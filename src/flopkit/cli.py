"""flopkit command line. Text output by default, ``--json`` for scripts. Exit codes:
0 = ok / allowed, 1 = error, 2 = refused or suspect (do not proceed)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import __version__, guard, pace, rules, verify
from .ledger import STATUSES, Ledger

DEFAULT_HOME = Path(os.environ.get("FLOPKIT_HOME", "."))


def _out(args, data, text: str) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else text)


def cmd_verify(args) -> int:
    allow = verify.Allowlist.from_file(args.allowlist) if args.allowlist else None
    results = [verify.check_url(u, allow) for u in args.urls]
    worst = 2 if any(r.verdict == verify.SUSPECT for r in results) else 0
    if args.strict and any(r.verdict != verify.OFFICIAL for r in results):
        worst = 2
    _out(args, [r.as_dict() for r in results],
         "\n".join(f"{r.verdict:<8} {r.url}  ({r.reason})" for r in results))
    return worst


def _ledger(args) -> Ledger:
    return Ledger(args.ledger or DEFAULT_HOME / "flopkit-ledger.jsonl")


def cmd_ledger_add(args) -> int:
    e = _ledger(args).add(args.session, args.amount, args.status, args.miner or "", args.source, args.note or "")
    _out(args, json.loads(e.to_json()), f"recorded {e.session_id}: {e.amount} {e.status}")
    return 0


def cmd_ledger_report(args) -> int:
    lg = _ledger(args)
    reps = [lg.report(d) for d in args.days]
    lines = [f"{r['days']:>3} d: settled {r['settled']} | pending {r['pending']} | disputed {r['disputed']} | "
             f"active days {r['active_days']} | miners {r['distinct_miners']}" for r in reps]
    _out(args, reps, "\n".join(lines))
    return 0


def cmd_pace(args) -> int:
    lg = Ledger(args.ledger) if args.ledger else None
    spent = args.spent if args.spent is not None else (lg.committed() if lg else 0)
    active7 = lg.report(7)["active_days"] if lg else None
    res = pace.plan(args.budget, spent, start=args.start, days=args.days, end=args.end, today=args.today,
                    margin=args.margin, floor=args.floor, active_days_last7=active7)
    text = (f"day {res['days_total'] - res['days_left'] + 1 if res['days_left'] else res['days_total']}/{res['days_total']} "
            f"| spent {res['spent']} of {res['budget']} | daily target {res['daily_target']} "
            f"| {res['days_left']} day(s) left")
    text += "".join(f"\n  ! {w}" for w in res["warnings"])
    _out(args, res, text)
    return 0


def cmd_guard(args) -> int:
    own = guard.OwnAddresses.load(args.own)
    lg = Ledger(args.ledger) if args.ledger else None
    d = guard.check(args.to, args.amount, own, sender=args.sender, daily_cap=args.daily_cap, ledger=lg)
    _out(args, d.as_dict(), ("ALLOW  " if d.allowed else "REFUSE ") + "; ".join(d.reasons))
    return d.code


def cmd_rules_show(args) -> int:
    data = rules.load(args.file)
    lines = [f"[{r['id']}] {r['text']}  (source: {r['source_id']}, read {r.get('read_on', '?')})" for r in data["rules"]]
    _out(args, data, "\n".join(lines))
    return 0


def cmd_rules_check(args) -> int:
    res = rules.check(rules.load(args.file), args.pages, args.online)
    _out(args, res, "\n".join(f"{r['status']:<12} {r['source']}" + (f"  -> re-read rules {r['rules']}" if r['status'] == 'CHANGED' else "") for r in res))
    return 2 if any(r["status"] == "CHANGED" for r in res) else 0


def cmd_rules_hash(args) -> int:
    h = rules.sha256_text(Path(args.page).read_text(encoding="utf-8", errors="replace"))
    _out(args, {"file": args.page, "sha256": h}, h)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flopkit", description="Stay eligible: verify official endpoints, keep a "
                                "settled-session ledger, pace your faucet, never self-deal.")
    p.add_argument("--version", action="version", version=f"flopkit {__version__}")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("verify", help="check that URLs are official FLOP / Technocore endpoints")
    v.add_argument("urls", nargs="+")
    v.add_argument("--allowlist", help="JSON allowlist overriding the built-in one")
    v.add_argument("--strict", action="store_true", help="exit 2 unless every URL is OFFICIAL")
    v.set_defaults(func=cmd_verify)

    lg = sub.add_parser("ledger", help="local ledger of compute sessions")
    lgs = lg.add_subparsers(dest="lcmd", required=True)
    a = lgs.add_parser("add", help="record a session or a status change")
    a.add_argument("--session", required=True)
    a.add_argument("--amount", help="required for a new session")
    a.add_argument("--status", choices=STATUSES, default="pending")
    a.add_argument("--miner")
    a.add_argument("--source", default="manual")
    a.add_argument("--note")
    a.add_argument("--ledger")
    a.set_defaults(func=cmd_ledger_add)
    r = lgs.add_parser("report", help="settled / pending / disputed totals")
    r.add_argument("--days", type=int, nargs="+", default=[7, 30, 90])
    r.add_argument("--ledger")
    r.set_defaults(func=cmd_ledger_report)

    pc = sub.add_parser("pace", help="spread a faucet budget evenly until the snapshot")
    pc.add_argument("--budget", required=True)
    pc.add_argument("--spent", help="default: settled + pending from --ledger")
    pc.add_argument("--start", type=date.fromisoformat)
    pc.add_argument("--end", type=date.fromisoformat)
    pc.add_argument("--days", type=int, default=90)
    pc.add_argument("--today", type=date.fromisoformat)
    pc.add_argument("--margin", default="0.10", help="reserve kept aside (default 0.10)")
    pc.add_argument("--floor", help="official minimum daily activity, once published")
    pc.add_argument("--ledger")
    pc.set_defaults(func=cmd_pace)

    g = sub.add_parser("guard", help="refuse self-dealing and over-cap spend before you sign")
    g.add_argument("--to", required=True)
    g.add_argument("--amount", required=True)
    g.add_argument("--own", required=True, help="own_addresses.json (private)")
    g.add_argument("--sender")
    g.add_argument("--daily-cap")
    g.add_argument("--ledger")
    g.set_defaults(func=cmd_guard)

    ru = sub.add_parser("rules", help="sourced rules and change detection")
    rus = ru.add_subparsers(dest="rcmd", required=True)
    s = rus.add_parser("show"); s.add_argument("--file", default=str(Path(__file__).with_name("rules.json"))); s.set_defaults(func=cmd_rules_show)
    c = rus.add_parser("check"); c.add_argument("--file", default=str(Path(__file__).with_name("rules.json")))
    c.add_argument("--pages", help="directory of saved official pages named <source_id>.html|.txt")
    c.add_argument("--online", action="store_true", help="fetch the official pages (allowlisted hosts only)")
    c.set_defaults(func=cmd_rules_check)
    h = rus.add_parser("hash"); h.add_argument("page"); h.set_defaults(func=cmd_rules_hash)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
