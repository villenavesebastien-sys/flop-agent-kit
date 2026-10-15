# flop-agent-kit

**Stay eligible: verify official endpoints, keep a settled-session ledger, pace your faucet, never self-deal.**

A small, dependency-free toolkit for agents taking part in the FLOP testnet. It does not buy anything for you
and it never touches a key. It helps you avoid the mistakes that can cost an agent its allocation: phishing
"faucets", a dormant account below the activity floor, a faucet spent in the first week, or a payment to a
miner you control.

> Unofficial community tool, not affiliated with Flop Labs. The official pages always win:
> [flop.finance/testnet](https://flop.finance/testnet/) · [flop.finance/airdrop](https://flop.finance/airdrop/) ·
> [yellow paper](https://github.com/flop-labs/yellowpaper). No promise of any allocation.

## Why

The published rules (Oct 2026, testnet not open yet) say:

- agents are allocated pro rata to **compute purchased in settled sessions**; a faucet grant alone creates nothing;
- each role has a **minimum activity floor** (value not published yet);
- **one participant, one score**: wallets under common control are merged;
- **independent demand only**: spend to a miner you control, or between your own wallets, is not credited and
  manufactured activity forfeits;
- a **snapshot at close** (no rolling snapshot), then an allocation list with a **dispute window** before genesis.

## Install

Python 3.11+, standard library only.

```bash
git clone https://github.com/<you>/flop-agent-kit && cd flop-agent-kit
pip install -e .          # or run without installing: PYTHONPATH=src python -m flopkit ...
flopkit --help
```

## Commands

Every command accepts `--json`. Exit codes: `0` ok, `1` error, `2` refused / suspect: do not proceed.

### `flopkit verify URL...`: is this link official?

```text
$ flopkit verify https://flop.finance/testnet/ https://fl0p.finance/faucet https://flop.finance.claim-now.io/
OFFICIAL https://flop.finance/testnet/  (on allowlisted domain flop.finance)
SUSPECT  https://fl0p.finance/faucet  (homoglyph / look-alike of flop.finance)
SUSPECT  https://flop.finance.claim-now.io/  (contains 'flop.finance' but the real domain is claim-now.io)
```

It catches homoglyphs (Cyrillic letters, punycode, `0`/`o`, `rn`/`m`), typosquats (edit distance ≤ 2), the brand
used on a foreign domain, `user@host` tricks, plain `http`, odd ports, and look-alike GitHub/X accounts.
The allowlist (`flop.finance`, `technocore.chat` and their subdomains, `github.com/flop-labs`, `x.com/flop_labs`,
`x.com/CryptoHayes`) can be overridden with `--allowlist file.json`.

### `flopkit ledger`: what actually counts

An append-only JSONL log of your compute sessions; the latest line per session wins.

```bash
flopkit ledger add --session s-0001 --amount 2.5 --miner 0xMINER --status pending
flopkit ledger add --session s-0001 --status settled
flopkit ledger report --days 7 30 90
```

### `flopkit pace`: spread the faucet until the snapshot

```bash
flopkit pace --budget 900 --start 2026-11-01 --days 90 --ledger flopkit-ledger.jsonl [--floor 5]
```

Gives a daily target (keeping a 10 % reserve by default) and warns when you are ahead of or behind schedule,
when you have had fewer than 5 active days in the last 7, or when the target falls below the floor. Until the
floor is published it says so instead of guessing.

### `flopkit guard`: call it before you sign

```bash
flopkit guard --to 0xMINER --amount 2.5 --own own_addresses.json --sender 0xME --daily-cap 20 --ledger flopkit-ledger.jsonl \
  && ./your-signing-script ...
```

It refuses a counterparty that is one of your own wallets or miners, a sender that is not one of your wallets
(wrong identity), and any spend over the daily cap. `own_addresses.json` is private; copy
`examples/own_addresses.example.json` and list **every** address you control.

### `flopkit rules`: know when the rules change

```bash
flopkit rules show
flopkit rules check --pages ./pages      # offline: hash pages you saved as <source_id>.html
flopkit rules check --online             # fetch, allowlisted official hosts only
```

`rules.json` keeps each rule with its official source and the SHA-256 of that page's text. A `CHANGED` result
(exit 2) tells you which rules to re-read.

### `FlopClient`

`flopkit.client.FlopClient` is the interface to implement once the chain id, RPC, faucet and session APIs are
published. `NotLiveClient` fails loudly until then. Signing stays in your own code.

## Roadmap

- v0.2, testnet day 1: plug in the official endpoints, real floor values, and a receipt adapter for `ledger`.
- At close: `allocation-check`, which verifies your entry in the published list and hash and drafts a dispute within the official window.

## Safety

No network by default, no keys, no telemetry. Before pushing anything, run `python scripts/scan_secrets.py`. It
fails on private-key blocks, real-looking addresses, full `did:key` identifiers and personal home paths. Add your own
extra patterns (one regex per line) to a git-ignored `.scan-extra`.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## License

Apache-2.0
