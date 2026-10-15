"""Pre-spend guard. Call it before signing any payment; a non-zero exit code means DO NOT SIGN.

Enforces the official "independent demand only" rule (flop.finance/testnet/ §06): spend routed to a
miner under your control, or circulated between your own wallets, is not demand and can forfeit the
allocation. Also enforces an optional daily cap.

own_addresses.json (private, never committed):
  {"wallets": ["0x..."], "miners": ["0x..."], "notes": "anything under my control"}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .ledger import Ledger, to_decimal

ALLOW, REFUSE = 0, 2


def norm(addr: str) -> str:
    return (addr or "").strip().lower()


@dataclass
class OwnAddresses:
    wallets: set[str] = field(default_factory=set)
    miners: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, path: str | Path) -> "OwnAddresses":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls({norm(a) for a in data.get("wallets", []) if a}, {norm(a) for a in data.get("miners", []) if a})

    @property
    def all(self) -> set[str]:
        return self.wallets | self.miners


@dataclass
class Decision:
    allowed: bool
    reasons: list[str]

    @property
    def code(self) -> int:
        return ALLOW if self.allowed else REFUSE

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "exit_code": self.code, "reasons": self.reasons}


def check(to: str, amount, own: OwnAddresses, sender: str | None = None, daily_cap=None,
          ledger: Ledger | None = None, day: str | None = None) -> Decision:
    reasons: list[str] = []
    t, s = norm(to), norm(sender or "")
    try:
        amt = to_decimal(amount)
    except ValueError as exc:
        return Decision(False, [str(exc)])
    if not t:
        reasons.append("no counterparty address")
    if amt == 0:
        reasons.append("amount is zero")
    if t and t in own.miners:
        reasons.append("counterparty is a miner under your control (self-dealing, not independent demand)")
    elif t and t in own.wallets:
        reasons.append("counterparty is one of your own wallets (circular spend, not independent demand)")
    if s and t and s == t:
        reasons.append("sender and counterparty are the same address")
    if s and own.all and s not in own.wallets:
        reasons.append("sender is not listed in your own wallets: check you are using the right identity")
    if daily_cap is not None:
        cap = to_decimal(daily_cap)
        today = day or datetime.now(timezone.utc).date().isoformat()
        already = ledger.spent_on(today) if ledger else Decimal(0)
        if already + amt > cap:
            reasons.append(f"daily cap exceeded: {already} already + {amt} > {cap}")
    return Decision(not reasons, reasons or ["ok: independent counterparty, within limits"])
