"""Offline URL check: is this link one of the official FLOP / Technocore endpoints?

Verdicts:
  OFFICIAL  - host (and path, where it matters) is on the allowlist
  UNKNOWN   - not on the allowlist, no sign of impersonation
  SUSPECT   - looks like an impersonation (homoglyph, typosquat, brand in a foreign domain,
              credentials trick, non-https), or an official host on a strange port

No network access. The allowlist is data you can extend (``Allowlist.from_file``).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

OFFICIAL = "OFFICIAL"
UNKNOWN = "UNKNOWN"
SUSPECT = "SUSPECT"

# Domains where any subdomain is also official.
DEFAULT_DOMAINS = ("flop.finance", "technocore.chat")
# Shared platforms: only these accounts / orgs are official (first path segment, case-insensitive).
DEFAULT_ACCOUNTS = {
    "github.com": ("flop-labs",),
    "x.com": ("flop_labs", "cryptohayes"),
    "twitter.com": ("flop_labs", "cryptohayes"),
}
BRAND_TOKENS = ("flop", "technocore", "flopfinance", "floplabs")

# Common confusables folded to ASCII before comparison (Latin look-alikes, digits, Cyrillic, Greek).
_CONFUSABLES = {
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "|": "l", "!": "i",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ӏ": "l", "ԁ": "d", "һ": "h", "ո": "n", "ս": "u", "ɡ": "g", "ⅼ": "l",
    "α": "a", "ο": "o", "ρ": "p", "ν": "v", "κ": "k", "τ": "t", "ι": "i",
}
_MULTI = (("rn", "m"), ("vv", "w"), ("cl", "d"))


def skeleton(text: str) -> str:
    """Fold a host to a comparison skeleton: NFKC, lower case, confusables, separators removed."""
    t = unicodedata.normalize("NFKC", text).lower()
    t = "".join(_CONFUSABLES.get(ch, ch) for ch in t)
    t = "".join(ch for ch in unicodedata.normalize("NFKD", t) if not unicodedata.combining(ch))
    t = t.replace("i", "l")  # i / l / 1 are interchangeable to the eye
    for a, b in _MULTI:
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", t)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@dataclass
class Allowlist:
    domains: tuple[str, ...] = DEFAULT_DOMAINS
    accounts: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_ACCOUNTS))

    @classmethod
    def from_file(cls, path: str | Path) -> "Allowlist":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(tuple(d.lower() for d in data.get("domains", DEFAULT_DOMAINS)),
                   {k.lower(): tuple(v.lower() for v in vs)
                    for k, vs in data.get("accounts", DEFAULT_ACCOUNTS).items()})


@dataclass
class Verdict:
    url: str
    verdict: str
    reason: str
    host: str = ""

    def as_dict(self) -> dict:
        return {"url": self.url, "verdict": self.verdict, "reason": self.reason, "host": self.host}


def _decode_host(raw: str) -> str:
    host = raw.strip().rstrip(".").lower()
    labels = []
    for label in host.split("."):
        if label.startswith("xn--"):
            try:
                label = label.encode("ascii").decode("idna")
            except UnicodeError:
                pass
        labels.append(label)
    return ".".join(labels)


def _on_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def check_url(url: str, allow: Allowlist | None = None) -> Verdict:
    allow = allow or Allowlist()
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        return Verdict(url, SUSPECT, f"malformed URL ({exc})")
    if parts.username or parts.password or "@" in parts.netloc:
        return Verdict(url, SUSPECT, "credentials or '@' in the address: the real host is after the '@'",
                       _decode_host(parts.hostname or ""))
    host = _decode_host(parts.hostname or "")
    if not host:
        return Verdict(url, SUSPECT, "no host")
    ascii_only = all(ord(c) < 128 for c in host)

    official_hosts = list(allow.domains) + list(allow.accounts)
    for domain in allow.domains:
        if _on_domain(host, domain):
            if not ascii_only:
                break
            if parts.scheme != "https":
                return Verdict(url, SUSPECT, f"official domain but scheme is {parts.scheme}, not https", host)
            if port not in (None, 443):
                return Verdict(url, SUSPECT, f"official domain on unusual port {port}", host)
            return Verdict(url, OFFICIAL, f"on allowlisted domain {domain}", host)

    bare = host[4:] if host.startswith("www.") else host
    if bare in allow.accounts and ascii_only:
        first = parts.path.strip("/").split("/")[0].lower()
        if parts.scheme != "https":
            return Verdict(url, SUSPECT, f"scheme is {parts.scheme}, not https", host)
        if first in allow.accounts[bare]:
            return Verdict(url, OFFICIAL, f"official account {bare}/{first}", host)
        for acct in allow.accounts[bare]:
            if first and levenshtein(skeleton(first), skeleton(acct)) <= 2:
                return Verdict(url, SUSPECT, f"account '{first}' imitates official '{acct}' on {bare}", host)
        if any(tok in first for tok in BRAND_TOKENS):
            return Verdict(url, SUSPECT, f"'{first}' on {bare} uses the brand but is not an official account", host)
        return Verdict(url, UNKNOWN, f"{bare} is a shared platform; '{first or '/'}' is not an official account", host)

    # Not official: look for impersonation.
    hs = skeleton(host)
    for off in official_hosts:
        os_ = skeleton(off)
        if hs == os_:
            return Verdict(url, SUSPECT, f"homoglyph / look-alike of {off}", host)
        if not ascii_only and os_ in hs:
            return Verdict(url, SUSPECT, f"non-ASCII host imitating {off}", host)
    labels = host.split(".")
    for off in allow.domains:
        # typosquat on the registrable part, e.g. fIop.finance, flop.flnance, flopp.finance
        tail = ".".join(labels[-len(off.split(".")):])
        if levenshtein(skeleton(tail), skeleton(off)) <= 2:
            return Verdict(url, SUSPECT, f"typosquat of {off} (edit distance <= 2)", host)
        # official name used as a subdomain of a foreign domain, e.g. flop.finance.claim-now.io
        if off in host and not _on_domain(host, off):
            return Verdict(url, SUSPECT, f"contains '{off}' but the real domain is {'.'.join(labels[-2:])}", host)
    tokens = re.split(r"[.\-_]", host)
    joined = skeleton(".".join(labels[:-1]))
    for tok in BRAND_TOKENS:
        if tok in tokens or joined.startswith(tok) or any(t.startswith(tok) and len(t) <= len(tok) + 8 for t in tokens):
            return Verdict(url, SUSPECT, f"uses the brand '{tok}' on a non-official domain", host)
    if not ascii_only:
        return Verdict(url, UNKNOWN, "non-ASCII host, not on the allowlist", host)
    return Verdict(url, UNKNOWN, "not on the allowlist", host)
