"""Pace a faucet budget over the testnet so spend stays regular until the snapshot.

Only settled compute counts, a minimum activity floor applies per role, and the snapshot is taken at
close (no rolling snapshot): front-loading the faucet and going dormant is the classic way to lose.
The official floor is unknown until the testnet rules are published, so ``floor=None`` warns instead
of guessing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal


@dataclass
class PacePlan:
    start: date
    end: date
    today: date
    budget: Decimal
    spent: Decimal
    margin: Decimal
    floor: Decimal | None
    active_days_last7: int | None = None

    @property
    def days_total(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def days_left(self) -> int:
        if self.today > self.end:
            return 0
        return (self.end - max(self.today, self.start)).days + 1

    def compute(self) -> dict:
        remaining = max(self.budget - self.spent, Decimal(0))
        usable = (remaining * (1 - self.margin)).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
        daily = (usable / self.days_left).quantize(Decimal("0.0001"), rounding=ROUND_DOWN) if self.days_left else Decimal(0)
        elapsed = max(0, min(self.days_total, (self.today - self.start).days + 1))
        expected = (self.budget * (1 - self.margin) * elapsed / self.days_total) if self.days_total else Decimal(0)
        warnings: list[str] = []
        if self.today < self.start:
            warnings.append("testnet not started yet")
        if self.today > self.end:
            warnings.append("testnet window is over")
        if self.floor is None:
            warnings.append("activity floor unknown: not published yet, re-check the official rules")
        elif self.days_left and daily < self.floor:
            warnings.append(f"daily target {daily} is BELOW the floor {self.floor}: budget too small or spent too fast")
        if self.spent > expected * Decimal("1.25") and elapsed < self.days_total:
            warnings.append("spending ahead of schedule: risk of running dry before the snapshot")
        if elapsed > 1 and self.spent < expected * Decimal("0.5"):
            warnings.append("spending well behind schedule: regular settled sessions matter")
        if self.active_days_last7 is not None and elapsed >= 7 and self.active_days_last7 < 5:
            warnings.append(f"only {self.active_days_last7} active day(s) in the last 7")
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "today": self.today.isoformat(),
                "days_total": self.days_total, "days_left": self.days_left, "budget": str(self.budget),
                "spent": str(self.spent), "remaining": str(remaining), "reserve_margin": str(self.margin),
                "daily_target": str(daily), "expected_spent_by_today": str(expected.quantize(Decimal("0.0001"))),
                "floor": None if self.floor is None else str(self.floor), "warnings": warnings}


def plan(budget, spent=0, start: date | None = None, days: int = 90, end: date | None = None,
         today: date | None = None, margin="0.10", floor=None, active_days_last7=None) -> dict:
    today = today or date.today()
    start = start or today
    end = end or (start + timedelta(days=days - 1))
    if end < start:
        raise ValueError("end before start")
    m = Decimal(str(margin))
    if not (Decimal(0) <= m < 1):
        raise ValueError("margin must be in [0, 1)")
    return PacePlan(start, end, today, Decimal(str(budget)), Decimal(str(spent)), m,
                    None if floor is None else Decimal(str(floor)), active_days_last7).compute()
