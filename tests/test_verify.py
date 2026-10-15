import unittest

from flopkit.verify import OFFICIAL, SUSPECT, UNKNOWN, check_url


class VerifyTests(unittest.TestCase):
    def v(self, url):
        return check_url(url).verdict

    def test_official(self):
        for url in ["https://flop.finance/testnet/", "flop.finance", "https://FLOP.FINANCE/airdrop/",
                    "https://gpus.flop.finance/", "https://technocore.chat/r/dev",
                    "https://challenges.technocore.chat/close-1/index.json",
                    "https://github.com/flop-labs/yellowpaper/issues/123", "https://x.com/flop_labs",
                    "https://twitter.com/CryptoHayes/status/1", "https://www.github.com/flop-labs/tclk"]:
            self.assertEqual(self.v(url), OFFICIAL, url)

    def test_lookalikes_are_suspect(self):
        for url in ["https://fl0p.finance/faucet", "https://flop.flnance/", "https://flopp.finance/",
                    "https://flop-finance.io/claim", "https://flopfinance.com/", "https://flop.finance.claim-now.io/",
                    "https://xn--flp-6cd.finance/",            # punycode with Cyrillic o
                    "https://flоp.finance/",               # raw Cyrillic o
                    "https://technocore.chat@evil.example/faucet",
                    "https://techn0core.chat/r/faucet", "https://technocore-chat.app/",
                    "https://github.com/flop-lab/airdrop", "https://github.com/flop-labs-official/claim",
                    "https://x.com/flop_lab", "https://x.com/flopIabs", "https://x.com/FlopAirdrop",
                    "http://flop.finance/testnet/", "https://flop.finance:8443/"]:
            self.assertEqual(self.v(url), SUSPECT, url)

    def test_unknown(self):
        for url in ["https://example.com/", "https://github.com/torvalds/linux", "https://x.com/someone",
                    "https://flipflop-shoes.example/"]:
            self.assertIn(self.v(url), (UNKNOWN,), url)

    def test_reason_present(self):
        r = check_url("https://fl0p.finance/")
        self.assertTrue(r.reason)


if __name__ == "__main__":
    unittest.main()
