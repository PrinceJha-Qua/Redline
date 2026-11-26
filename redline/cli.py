"""redline check brief.txt | redline query "MATCH ..." | redline serve | redline mcp"""
import argparse
import json
import sys

COLOURS = {"VERIFIED": "\033[32m", "FABRICATED": "\033[31m", "UNVERIFIABLE": "\033[33m"}
STATUS = {"overruled": "\033[31m", "overruled in part": "\033[31m", "caution": "\033[33m", "good law": "\033[32m"}
RESET = "\033[0m"


def _paint(text, colour, on):
    return f"{colour}{text}{RESET}" if on and colour else text


def cmd_check(args):
    from . import service
    text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
    result = service.check_text(text, args.as_of)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result["summary"]["fabricated"] else 0
    on = sys.stdout.isatty() and not args.no_colour
    for c in result["citations"]:
        verdict = _paint(f"{c['verdict']:<12}", COLOURS.get(c["verdict"]), on)
        status = _paint(f"{(c['status'] or ''):<17}", STATUS.get(c["status"]), on)
        print(f"{verdict} {status} {c['text']}")
        print(f"             {c['reason']}")
        for w in c["warnings"]:
            print(f"             ! {w}")
        for g in c.get("suggestions") or []:
            print(f"             → did you mean {g['name']}, {g['cite']} ({g['court']} {g['year']})?")
        for ch in c["stands_on"][:3]:
            line = f"             └ stands on {ch['case']['name']}, {ch['case']['cite']} → overruled by " \
                   f"{ch['overruled_by']['name']} ({ch['overruled_by']['year']})"
            print(line)
    s = result["summary"]
    print(f"\n{s['citations']} citations: {s['verified']} verified ({s['overruled']} overruled, {s['caution']} caution), "
          f"{s['fabricated']} fabricated, {s['unverifiable']} unverifiable")
    return 1 if s["fabricated"] else 0


def cmd_authority(args):
    from . import service
    r = service.find_authority(args.proposition, args.circuit, args.limit, args.as_of)
    if args.json:
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0
    for a in r["authorities"]:
        c = a["case"]
        print(f"{c['name']}, {c['cite']} ({c['year']})  [{a['status']}]")
        for d in a["described_as"]:
            print(f"    {d['by']['court']}: ({d['parenthetical']})  — {d['by']['name']}, {d['by']['cite']}")
    if r["circuit_opinions"]:
        print(f"\n{r['circuit']} opinions:")
        for o in r["circuit_opinions"]:
            print(f"    {o['case']['name']}, {o['case']['cite']} ({o['case']['year']}): ({o['said']})")
    return 0


def cmd_what_if(args):
    from . import service
    text = open(args.brief, encoding="utf-8").read() if args.brief else None
    r = service.what_if(args.case_id, text)
    if not r:
        print(f"No case with id {args.case_id}.", file=sys.stderr)
        return 2
    print(f"If {r['case']['name']} ({r['case']['cite']}) were overruled: {r['relying']:,} of the {r['citing']:,} "
          f"decisions citing it rely on it.")
    for court, n in list(r["relying_by_court"].items())[:8]:
        print(f"    {court:<10} {n}")
    if r["brief"]:
        for ch in r["brief"]["changed"] or [{"text": "nothing", "before": "-", "after": "-"}]:
            print(f"  brief: {ch['text']}: {ch['before']} → {ch['after']}")
    print(f"({r['how']} Rolled back: {r['rolled_back']}.)")
    return 0


def cmd_query(args):
    from .store import Store
    rows = Store().query(args.cypher)
    print(json.dumps(rows[:args.limit], indent=2, ensure_ascii=False, default=str))
    if len(rows) > args.limit:
        print(f"... {len(rows) - args.limit} more rows (raise --limit to see them)", file=sys.stderr)


def cmd_serve(args):
    import uvicorn
    uvicorn.run("redline.api:app", host=args.host, port=args.port)


def cmd_mcp(args):
    from .mcp_server import mcp
    mcp.run("stdio")


def main(argv=None):
    p = argparse.ArgumentParser(prog="redline", description="Catch fabricated and overruled case citations.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check the citations in a file (or - for stdin); exits 1 if any are fabricated")
    c.add_argument("file")
    c.add_argument("--json", action="store_true")
    c.add_argument("--no-colour", action="store_true")
    c.add_argument("--as-of", help="check as of a year or date, such as the filing date")
    c.set_defaults(fn=cmd_check)
    a = sub.add_parser("authority", help="real cases courts have cited for a proposition")
    a.add_argument("proposition")
    a.add_argument("--circuit")
    a.add_argument("--limit", type=int, default=5)
    a.add_argument("--as-of")
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_authority)
    w = sub.add_parser("what-if", help="overrule a case hypothetically (rolled back) and see what relies on it")
    w.add_argument("case_id")
    w.add_argument("--brief", help="a brief to re-check under the hypothetical overruling")
    w.set_defaults(fn=cmd_what_if)
    q = sub.add_parser("query", help="run read-only Cypher against the store and print JSON")
    q.add_argument("cypher")
    q.add_argument("--limit", type=int, default=25)
    q.set_defaults(fn=cmd_query)
    s = sub.add_parser("serve", help="web app, API and MCP over HTTP")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)
    m = sub.add_parser("mcp", help="MCP server over stdio")
    m.set_defaults(fn=cmd_mcp)
    args = p.parse_args(argv)
    sys.exit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
