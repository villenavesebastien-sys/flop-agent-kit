#!/usr/bin/env python3
"""Pre-push secret scan. Exit 1 if anything that looks private is found.

Flags: private-key blocks, 32-byte hex keys, real-looking 0x addresses (fictional repeated-digit
examples such as 0x1111...1111 are allowed), full-length did:key identifiers, personal home paths,
and any extra pattern listed (one regex per line) in the optional, git-ignored file `.scan-extra`.
Run:  python scripts/scan_secrets.py [ROOT]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "build", "dist", ".pytest_cache"}
SKIP_FILES = {"LICENSE"}

# Built from pieces so this file does not flag itself.
PATTERNS = {
    "private key block": re.compile("-----BEGIN " + r"[A-Z ]*PRIVATE KEY-----"),
    "32-byte hex secret": re.compile(r"\b0x" + r"[0-9a-fA-F]{64}\b"),
    "wallet address": re.compile(r"\b0x" + r"[0-9a-fA-F]{40}\b"),
    "did:key identifier": re.compile("did:" + r"key:z6Mk[1-9A-HJ-NP-Za-km-z]{40,}"),
    "home path (Windows)": re.compile(r"[A-Za-z]:\\\\?Users\\\\?" + r"[A-Za-z0-9._-]+"),
    "home path (macOS/Linux)": re.compile(r"/(?:Users|home)/" + r"(?!runner\b|user\b|you\b|me\b)[a-z][a-z0-9._-]+"),
    "mnemonic hint": re.compile(r"(?i)\b(seed|mnemonic|secret)\s*(phrase)?\s*[:=]\s*\S+"),
}


def fictional_address(addr: str) -> bool:
    body = addr[2:].lower()
    return len(set(body)) == 1


def scan(root: Path) -> list[tuple[str, int, str, str]]:
    extra = []
    extra_file = root / ".scan-extra"
    if extra_file.exists():
        extra = [re.compile(l.strip()) for l in extra_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    hits = []
    for path in sorted(root.rglob("*")):
        if path.is_dir() or any(p in SKIP_DIRS for p in path.relative_to(root).parts):
            continue
        if path.name in SKIP_FILES or path.name == ".scan-extra":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for label, rx in PATTERNS.items():
                for m in rx.finditer(line):
                    if label == "wallet address" and fictional_address(m.group(0)):
                        continue
                    if label == "32-byte hex secret" and fictional_address(m.group(0)):
                        continue
                    hits.append((str(path.relative_to(root)), n, label, m.group(0)[:24] + "..."))
            for rx in extra:
                if rx.search(line):
                    hits.append((str(path.relative_to(root)), n, "custom pattern", rx.pattern[:24]))
    return hits


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
    hits = scan(root)
    for f, n, label, snippet in hits:
        print(f"{f}:{n}: {label}: {snippet}")
    print(f"secret scan: {len(hits)} finding(s) in {root.name}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
