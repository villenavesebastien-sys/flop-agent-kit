import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from flopkit import guard, pace
from flopkit.ledger import Ledger

EX = Path(__file__).resolve().parents[1] / "examples"


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lg = Ledger(Path(self.tmp.name) / "l.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_latest_status_wins_and_report(self):
        now = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
        self.lg.add("a", "2", "pending", miner="m1", ts=now - timedelta(days=1, minutes=5))
        self.lg.add("a", None, "settled", ts=now - timedelta(days=1))
        self.lg.add("b", "1.5", "settled", miner="m2", ts=now - timedelta(days=2))
        self.lg.add("c", "4", "disputed", miner="m1", ts=now - timedelta(days=3))
        self.lg.add("old", "9", "settled", ts=now - timedelta(days=40))
        r7 = self.lg.report(7, now=now)
        self.assertEqual(r7["settled"], "3.5")
        self.assertEqual(r7["disputed"], "4")
        self.assertEqual(r7["active_days"], 2)
        self.assertEqual(r7["distinct_miners"], 2)
        self.assertEqual(self.lg.report(90, now=now)["settled"], "12.5")
        self.assertEqual(len(self.lg.entries()), 5)  # append-only

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            self.lg.add("x", "-1")
        with self.assertRaises(ValueError):
            self.lg.add("x", "1", "paid")
        with self.assertRaises(ValueError):
            self.lg.add("new", None)

    def test_example_file_parses(self):
        lg = Ledger(EX / "ledger.example.jsonl")
        self.assertEqual(lg.sessions()["s-0001"].status, "settled")


class PaceTests(unittest.TestCase):
    def test_even_budget_over_90_days(self):
        r = pace.plan(900, 0, start=date(2026, 11, 1), days=90, today=date(2026, 11, 1), margin="0.10")
        self.assertEqual(r["days_total"], 90)
        self.assertEqual(r["days_left"], 90)
        self.assertEqual(Decimal(r["daily_target"]), Decimal("9"))
        self.assertTrue(any("floor unknown" in w for w in r["warnings"]))

    def test_midway_and_floor(self):
        r = pace.plan(900, 600, start=date(2026, 11, 1), days=90, today=date(2026, 12, 15), margin="0", floor="10")
        self.assertEqual(r["days_left"], 46)
        self.assertLess(Decimal(r["daily_target"]), Decimal(10))
        self.assertTrue(any("BELOW the floor" in w for w in r["warnings"]))

    def test_front_loading_warning(self):
        r = pace.plan(900, 500, start=date(2026, 11, 1), days=90, today=date(2026, 11, 10))
        self.assertTrue(any("ahead of schedule" in w for w in r["warnings"]))

    def test_after_end(self):
        r = pace.plan(900, 0, start=date(2026, 11, 1), days=90, today=date(2027, 3, 1))
        self.assertEqual(r["days_left"], 0)
        self.assertEqual(r["daily_target"], "0")


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.own = guard.OwnAddresses.load(EX / "own_addresses.example.json")
        self.me = "0x1111111111111111111111111111111111111111"

    def test_refuses_own_wallet_and_own_miner(self):
        d = guard.check("0x2222222222222222222222222222222222222222", 1, self.own, sender=self.me)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, 2)
        d = guard.check("0x3333333333333333333333333333333333333333".upper().replace("0X", "0x"), 1, self.own)
        self.assertFalse(d.allowed)
        self.assertIn("miner under your control", d.reasons[0])

    def test_allows_independent_miner(self):
        d = guard.check("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "2.5", self.own, sender=self.me)
        self.assertTrue(d.allowed, d.reasons)
        self.assertEqual(d.code, 0)

    def test_daily_cap(self):
        with tempfile.TemporaryDirectory() as t:
            lg = Ledger(Path(t) / "l.jsonl")
            day = datetime.now(timezone.utc).date().isoformat()
            lg.add("s1", "8", "settled")
            d = guard.check("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "3", self.own, daily_cap="10", ledger=lg, day=day)
            self.assertFalse(d.allowed)
            d = guard.check("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "2", self.own, daily_cap="10", ledger=lg, day=day)
            self.assertTrue(d.allowed)

    def test_wrong_sender_identity(self):
        d = guard.check("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", 1, self.own,
                        sender="0x9999999999999999999999999999999999999999")
        self.assertFalse(d.allowed)


if __name__ == "__main__":
    unittest.main()
