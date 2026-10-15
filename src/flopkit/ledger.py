"""Local, append-only ledger of compute sessions (JSONL).

Only compute bought in *settled* sessions counts toward an agent allocation (flop.finance/airdrop/),
so the ledger tracks each session's status over time. Every change is a new line; the latest line
for a ``session_id`` wins. Nothing is ever rewritten or deleted.

Line format:
  {"ts": "2026-11-02T10:00:00+00:00", "session_id": "...", "miner": "...", "amount": "1.5",
   "status": "pending|settled|disputed|refunded", "source": "manual|adapter-name", "note": "..."}
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

STATUSES = ("pending", "settled", "disputed", "refunded")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def to_decimal(value) -> Decimal:
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {value!r}") from exc
    if d < 0:
        raise ValueError("amount must be >= 0")
    return d


@dataclass
class Entry:
    ts: datetime
    session_id: str
    miner: str
    amount: Decimal
    status: str
    source: str = "manual"
    note: str = ""

    def to_json(self) -> str:
        return json.dumps({"ts": self.ts.isoformat(), "session_id": self.session_id, "miner": self.miner,
                           "amount": str(self.amount), "status": self.status, "source": self.source,
                           "note": self.note}, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "Entry":
        return cls(parse_ts(d["ts"]), str(d["session_id"]), str(d.get("miner", "")), to_decimal(d["amount"]),
                   d["status"], d.get("source", "manual"), d.get("note", ""))


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def entries(self) -> list[Entry]:
        if not self.path.exists():
            return []
        out = []
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    out.append(Entry.from_dict(json.loads(line)))
                except (ValueError, KeyError) as exc:
                    raise ValueError(f"{self.path}:{n}: bad ledger line ({exc})") from exc
        return out

    def sessions(self) -> dict[str, Entry]:
        """Latest state of each session (latest timestamp wins, file order breaks ties)."""
        latest: dict[str, Entry] = {}
        for e in self.entries():
            cur = latest.get(e.session_id)
            if cur is None or e.ts >= cur.ts:
                latest[e.session_id] = e
        return latest

    def add(self, session_id: str, amount, status: str = "pending", miner: str = "", source: str = "manual",
            note: str = "", ts: datetime | None = None) -> Entry:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        if not session_id:
            raise ValueError("session_id is required")
        prev = self.sessions().get(session_id)
        if prev is not None:
            miner = miner or prev.miner
            if amount is None:
                amount = prev.amount
        if amount is None:
            raise ValueError("amount is required for a new session")
        e = Entry(ts or _now(), session_id, miner, to_decimal(amount), status, source, note)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(e.to_json() + "\n")
        return e

    def report(self, days: int, now: datetime | None = None) -> dict:
        now = now or _now()
        since = now - timedelta(days=days)
        totals = {s: Decimal(0) for s in STATUSES}
        counts = {s: 0 for s in STATUSES}
        active_days: set[str] = set()
        miners: set[str] = set()
        for e in self.sessions().values():
            if e.ts < since or e.ts > now:
                continue
            totals[e.status] += e.amount
            counts[e.status] += 1
            if e.status == "settled":
                active_days.add(e.ts.date().isoformat())
                if e.miner:
                    miners.add(e.miner)
        return {"days": days, "since": since.isoformat(), "settled": str(totals["settled"]),
                "pending": str(totals["pending"]), "disputed": str(totals["disputed"]),
                "refunded": str(totals["refunded"]), "sessions": counts,
                "active_days": len(active_days), "distinct_miners": len(miners)}

    def spent_on(self, day: str) -> Decimal:
        """Settled + pending spend on a UTC day (YYYY-MM-DD), used by the guard's daily cap."""
        return sum((e.amount for e in self.sessions().values()
                    if e.ts.date().isoformat() == day and e.status in ("settled", "pending")), Decimal(0))

    def committed(self) -> Decimal:
        return sum((e.amount for e in self.sessions().values() if e.status in ("settled", "pending")),
                   Decimal(0))
