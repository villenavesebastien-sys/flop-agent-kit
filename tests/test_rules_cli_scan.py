import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from flopkit import cli, rules
from flopkit.client import NotLiveClient

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "src" / "flopkit" / "rules.json"


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


class RulesTests(unittest.TestCase):
    def test_rules_load_and_sources_official(self):
        data = rules.load(RULES)
        self.assertGreaterEqual(len(data["rules"]), 6)

    def test_change_detection_from_local_pages(self):
        data = rules.load(RULES)
        with tempfile.TemporaryDirectory() as t:
            Path(t, "testnet.html").write_text("<html><body><h1>Testnet</h1> rules v1</body></html>", encoding="utf-8")
            res = {r["source"]: r for r in rules.check(data, t)}
            self.assertEqual(res["testnet"]["status"], "NO_BASELINE")
            self.assertEqual(res["airdrop"]["status"], "NOT_CHECKED")
            data["sources"][0]["sha256"] = res["testnet"]["sha256"]
            self.assertEqual(rules.check(data, t)[0]["status"], "UNCHANGED")
            Path(t, "testnet.html").write_text("<p>Testnet rules v2: floor = 5</p>", encoding="utf-8")
            self.assertEqual(rules.check(data, t)[0]["status"], "CHANGED")

    def test_markup_noise_ignored(self):
        self.assertEqual(rules.sha256_text("<p>a  b</p>"), rules.sha256_text("a b"))

    def test_online_fetch_refuses_non_official(self):
        with self.assertRaises(PermissionError):
            rules.fetch_official("https://flop-finance.io/testnet/")


class CliTests(unittest.TestCase):
    def test_verify_exit_codes(self):
        self.assertEqual(run("verify", "https://flop.finance/testnet/")[0], 0)
        self.assertEqual(run("verify", "https://fl0p.finance/")[0], 2)
        self.assertEqual(run("verify", "--strict", "https://example.com")[0], 2)

    def test_guard_cli(self):
        own = str(ROOT / "examples" / "own_addresses.example.json")
        code, out = run("--json", "guard", "--to", "0x2222222222222222222222222222222222222222", "--amount", "1", "--own", own)
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["allowed"])

    def test_ledger_and_pace_cli(self):
        with tempfile.TemporaryDirectory() as t:
            lg = str(Path(t) / "l.jsonl")
            self.assertEqual(run("ledger", "add", "--session", "s1", "--amount", "3", "--status", "settled", "--ledger", lg)[0], 0)
            code, out = run("--json", "ledger", "report", "--days", "7", "--ledger", lg)
            self.assertEqual(json.loads(out)[0]["settled"], "3")
            code, out = run("--json", "pace", "--budget", "900", "--ledger", lg)
            self.assertEqual(json.loads(out)["spent"], "3")

    def test_bad_input_returns_1(self):
        self.assertEqual(run("guard", "--to", "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "--amount", "1", "--own", "/nonexistent.json")[0], 1)


class ClientTests(unittest.TestCase):
    def test_not_live(self):
        with self.assertRaises(NotImplementedError):
            NotLiveClient().chain_id()


class ScanTests(unittest.TestCase):
    def test_repo_is_clean(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "scan_secrets.py"), str(ROOT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_scan_catches_secrets(self):
        with tempfile.TemporaryDirectory() as t:
            key = "-----BEGIN " + "PRIVATE KEY-----"
            addr = "0x" + "52908400098527886E0F7030069857D2E4169EE7"
            did = "did:" + "key:z6Mk" + "hdmFqwUuzvKvBvQYqUNSnVK1QwWE8hdmFqwUuzvK"
            home = "C:" + "\\Users\\" + "somebody\\x"
            Path(t, "leak.txt").write_text("\n".join([key, addr, did, home]), encoding="utf-8")
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "scan_secrets.py"), t], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("4 finding", r.stdout)


if __name__ == "__main__":
    unittest.main()
