"""Versioned, sourced rules.

rules.json keeps each rule with the official page it comes from, the date it was read and the
SHA-256 of that page's text at the time. ``check`` tells you when a source page has changed since,
so you re-read it instead of trusting a stale assumption.

Offline by default: ``check`` hashes local copies you saved (``--pages DIR`` with files named after
the rule's ``source_id``). ``--online`` fetches the pages, and only from allowlisted official hosts.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path

from .verify import OFFICIAL, check_url


def normalize_text(text: str) -> str:
    """Hash what a human reads, not markup noise: strip tags/scripts, collapse whitespace."""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def load(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = {s["id"] for s in data.get("sources", [])}
    for r in data.get("rules", []):
        if r.get("source_id") not in ids:
            raise ValueError(f"rule {r.get('id')} points to unknown source {r.get('source_id')}")
    for s in data.get("sources", []):
        if check_url(s["url"]).verdict != OFFICIAL:
            raise ValueError(f"source {s['id']} is not an official URL: {s['url']}")
    return data


def fetch_official(url: str, timeout: int = 20) -> str:
    if check_url(url).verdict != OFFICIAL:
        raise PermissionError(f"refusing to fetch non-official URL {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "flop-agent-kit (rules check)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - allowlisted above
        return resp.read().decode("utf-8", errors="replace")


def check(data: dict, pages_dir: str | Path | None = None, online: bool = False) -> list[dict]:
    out = []
    for s in data.get("sources", []):
        text, how = None, None
        if pages_dir:
            for cand in Path(pages_dir).glob(f"{s['id']}.*"):
                text, how = cand.read_text(encoding="utf-8", errors="replace"), f"file {cand.name}"
                break
        if text is None and online:
            text, how = fetch_official(s["url"]), "online"
        if text is None:
            out.append({"source": s["id"], "status": "NOT_CHECKED", "detail": "no local copy (use --pages or --online)"})
            continue
        h = sha256_text(text)
        if not s.get("sha256"):
            status = "NO_BASELINE"
        else:
            status = "UNCHANGED" if h == s["sha256"] else "CHANGED"
        out.append({"source": s["id"], "status": status, "sha256": h, "recorded": s.get("sha256"), "via": how,
                    "rules": [r["id"] for r in data.get("rules", []) if r["source_id"] == s["id"]]})
    return out
