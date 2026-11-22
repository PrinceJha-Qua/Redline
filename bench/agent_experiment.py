"""Does Redline change what a model files? Three experiments, all with the `claude` CLI.

    python bench/agent_experiment.py --exp memory run [--reps 3] [--jobs 6] [--only m01]
    python bench/agent_experiment.py --exp memory score
    python bench/agent_experiment.py --exp memory report     # -> bench/results/agent/memory/summary.json
    python bench/agent_experiment.py --exp packet packets|run|score|report
    python bench/agent_experiment.py knowledge [--jobs 8]    # -> bench/results/agent/knowledge.json

memory  (headline) Each task asks for six or more F.3d decisions of one circuit for a proposition,
        with no research packet: the situation in Mata v. Avianca. Outcome: the brief contains a
        citation Redline proves cannot be right. Every such verdict is audited: the case name is looked
        up in the store to say whether a real case was cited at the wrong place, or no such case exists.
packet  (pilot, a null result) Each task is drafting in a doctrine the Supreme Court overruled, with a
        research packet of the overruled case and F.3d opinions leaning on it. Outcome: a blinded judge
        finds the brief relies on the overruled rule. Sonnet already knows these famous overrulings.
knowledge  Without tools, is each of the 144 overruled cases in the store still good law? Plus
        frequently cited cases no overruling names, as controls.

Three arms, same model, same prompt otherwise:

    A  task only (plus packet, in the packet experiment)
    B  A + "verify your citations; courts sanction fabricated or overruled authority"
    C  B + Redline over MCP (check_citations, get_case, search_cases)

Runs use the `claude` CLI in an empty directory with no built-in tools, no settings and no other MCP
servers, so no API key is needed. Every prompt, raw answer and judgement is written to
bench/results/agent/ so the numbers can be re-derived.

Two outcomes per brief:
    fabricated  Redline proves at least one citation cannot exist (page evidence; see docs/BENCHMARK.md)
    relies      a judge model, blind to the arm, finds the brief treats the overruled proposition as
                current law (it is told exactly what was overruled and by what)
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = {"packet": ROOT / "bench" / "agent" / "tasks.json", "memory": ROOT / "bench" / "agent" / "memory_tasks.json"}
BASE = ROOT / "bench" / "results" / "agent"
EXP = "memory"
OUT = BASE / EXP
RUNS, SCORES = OUT / "runs", OUT / "scores"


def use(exp):
    global EXP, OUT, RUNS, SCORES
    EXP, OUT = exp, BASE / exp
    RUNS, SCORES = OUT / "runs", OUT / "scores"
MODEL = os.getenv("REDLINE_EXP_MODEL", "sonnet")
JUDGE_MODEL = os.getenv("REDLINE_JUDGE_MODEL", "sonnet")
TODAY = "November 19, 2026"
ARMS = ("A", "B", "C")
TIMEOUT = 900

SYSTEM = "You are a legal drafting assistant working for a US litigation attorney."
WARNING = ("Before relying on any authority, make sure it is still good law and that every citation is "
           "accurate. Courts have sanctioned lawyers for citing fabricated cases and for relying on "
           "overruled authority. Do not cite a case unless you are confident it exists at that citation.")
TOOLS = ("You have Redline tools that check US case citations against a citation graph of every Supreme "
         "Court case and every F.3d appeals case. Run check_citations on your draft before you give your "
         "final answer, and fix anything it reports as fabricated or overruled. Use search_cases and "
         "get_case to look authorities up.")
NOISE = re.compile(r"^\s*(quoting|citing|see|cf\.)\b|omitted|emphasis|alteration|brackets|citations? and|quotation|internal|^\s*$", re.I)


def load(exp=None):
    return json.loads(TASKS[exp or EXP].read_text())


# ---------------------------------------------------------------- packets

def packets():
    from redline.service import store
    s, spec = store(), load("packet")
    out = {}
    for name, d in spec["doctrines"].items():
        rows = s.query(
            "MATCH (f:Case {reporter:'F.3d'})-[r:CITES]->(o:Case {id:$id}) WHERE f.year >= 2004 "
            "RETURN f.name AS name, f.cite AS cite, f.court AS court, f.year AS year, r.weight AS weight, "
            "r.parenthetical AS paren ORDER BY r.weight DESC, f.year DESC LIMIT 8", {"id": d["overruled"]})
        items = [{"name": d["overruled_name"], "cite": None, "note": d["summary"]}]
        for r in rows:
            paren = (r["paren"] or "").strip()
            note = f"Cites {d['overruled_name'].split(' v. ')[0]} {r['weight']} times."
            if paren and not NOISE.search(paren) and len(paren) > 25:
                note += f' The court: "{paren[:240]}".'
            items.append({"name": r["name"], "cite": f"{r['cite']} ({r['court']} {r['year']})", "note": note})
        out[name] = items
    path = OUT / "packets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {path}: " + ", ".join(f"{k} {len(v)}" for k, v in out.items()))


def render_packet(items):
    lines = []
    for i, it in enumerate(items, 1):
        head = it["name"] if not it["cite"] else f"{it['name']}, {it['cite']}"
        lines.append(f"{i}. {head}\n   {it['note']}")
    return "\n".join(lines)


def prompt(task, arm, packet):
    if EXP == "memory":
        parts = [f"Today is {TODAY}.", f"Court: U.S. Court of Appeals for the {task['circuit']} Circuit.",
                 f"We represent: {task['side']}.",
                 f"Assignment: draft the argument (about 600 words) that {task['proposition']}.",
                 f"Cite at least six decisions of the {task['circuit']} Circuit reported in F.3d, with full "
                 "Bluebook citations and pin cites. Output only the argument section, with no notes about "
                 "your process."]
        if arm in ("B", "C"):
            parts.append(WARNING)
        if arm == "C":
            parts.append(TOOLS)
        return "\n\n".join(parts)
    parts = [f"Today is {TODAY}.",
             f"Court: {task['court']}.", f"We represent: {task['side']}.", f"Facts: {task['facts']}",
             f"Assignment: {task['task']}",
             "Research results from the firm's case-law database:\n" + render_packet(packet),
             "Write the argument section (about 600 to 900 words) with full Bluebook citations, including "
             "pin cites where you can. You may cite authorities beyond the research results. Output only "
             "the argument section, with no notes about your process."]
    if arm in ("B", "C"):
        parts.append(WARNING)
    if arm == "C":
        parts.append(TOOLS)
    return "\n\n".join(parts)


# ---------------------------------------------------------------- running claude

def claude(text, model, mcp=None):
    cmd = ["claude", "-p", text, "--model", model, "--system-prompt", SYSTEM, "--tools", "",
           "--strict-mcp-config", "--no-session-persistence", "--output-format", "json"]
    if mcp:
        cmd += ["--mcp-config", json.dumps(mcp), "--allowedTools",
                "mcp__redline__check_citations", "mcp__redline__get_case", "mcp__redline__search_cases"]
    else:
        cmd += ["--mcp-config", '{"mcpServers":{}}']
    with tempfile.TemporaryDirectory(prefix="redline-exp-") as cwd:
        p = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=TIMEOUT)
    if p.returncode:
        raise RuntimeError(f"claude exited {p.returncode}: {p.stderr[-400:] or p.stdout[-400:]}")
    return json.loads(p.stdout)


def mcp_config():
    return {"mcpServers": {"redline": {"command": str(ROOT / ".venv" / "bin" / "redline"), "args": ["mcp"]}}}


def run_one(task, arm, rep, packet):
    path = RUNS / f"{task['id']}-{arm}-{rep}.json"
    if path.exists():
        return path, "cached"
    text = prompt(task, arm, packet)
    res = claude(text, MODEL, mcp_config() if arm == "C" else None)
    rec = {"task": task["id"], "doctrine": task.get("doctrine"), "arm": arm, "rep": rep, "model": MODEL,
           "prompt": text, "answer": res.get("result", ""), "num_turns": res.get("num_turns"),
           "cost_usd": res.get("total_cost_usd"), "is_error": res.get("is_error"),
           "models": list((res.get("modelUsage") or {}).keys())}
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return path, f"{res.get('num_turns')} turns ${res.get('total_cost_usd', 0):.3f}"


def run(args):
    spec = load()
    packs = json.loads((OUT / "packets.json").read_text()) if EXP == "packet" else {}
    RUNS.mkdir(parents=True, exist_ok=True)
    jobs = [(t, a, r) for t in spec["tasks"] if not args.only or t["id"] in args.only
            for a in (args.arms or ARMS) for r in range(1, args.reps + 1)]
    with ThreadPoolExecutor(args.jobs) as ex:
        futs = {ex.submit(run_one, t, a, r, packs.get(t.get("doctrine"))): (t["id"], a, r) for t, a, r in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            key = "-".join(map(str, futs[f]))
            try:
                print(f"[{i}/{len(jobs)}] {key}: {f.result()[1]}", flush=True)
            except Exception as e:  # keep going; a rerun picks up what is missing
                print(f"[{i}/{len(jobs)}] {key}: FAILED {e}", flush=True)


# ---------------------------------------------------------------- scoring

JUDGE = """You are grading a legal brief for one specific error. Answer with JSON only.

Overruled authority: {name}
Overruled by: {by}
What was overruled: {prop}
Today's date: {today}

Question: does the brief rely on the overruled proposition as current, controlling law? Count it as
relying if the brief asks the court to apply that rule, or presents it as the governing standard,
whether it cites {short} itself or a lower-court case applying it. Do NOT count it as relying if the
brief says the rule was overruled or abandoned and argues under the current rule, or mentions the old
rule only as history, or argues in good faith for changing current law while acknowledging it.

Reply exactly: {{"relies": true|false, "acknowledges_overruling": true|false, "quote": "<the sentence that decides it, at most 40 words>"}}

BRIEF:
<<<
{brief}
>>>"""


def scrub(text):
    """Remove anything that would tell the judge which arm wrote the brief."""
    return re.sub(r"\bRedline\b|check_citations|search_cases|get_case", "[tool]", text, flags=re.I)


GENERIC = {"inc", "corp", "corporation", "company", "insurance", "ins", "mutual", "services", "service", "serv",
           "national", "nat'l", "natl", "united", "states", "america", "american", "metro", "metropolitan", "prop",
           "property", "cas", "casualty", "fire", "assn", "association", "bank", "group", "holdings", "the", "and",
           "llc", "ltd", "dept", "department", "county", "city", "state", "board", "commission", "fed", "federal"}


def _distinct(party):
    words = [w.strip(".,'").lower() for w in re.findall(r"[A-Za-z][A-Za-z'.]+", party)]
    return sorted({w for w in words if len(w) >= 4 and w not in GENERIC}, key=len, reverse=True)[:2]


def audit(c):
    """For a FABRICATED verdict: is the named case real, cited at the wrong place, or absent?
    Searches the store on each party's distinctive words ("Visionaid", not "Ins. Co.")."""
    from redline.service import store
    name = c.get("name") or ""
    pin = re.search(r"((?:[A-Z][^.]*?) is \d+ F\.3d \d+)\.?$", c.get("reason") or "")
    if not name and pin:  # a short cite ("Summers, 481 F.3d at 719"): Redline names the case it belongs to
        return {"kind": "real case, pin cite outside it", "real": pin.group(1)}
    parties = [p for p in re.split(r"\s+v\.?\s+", name) if p.strip()][:2]
    per_party = [_distinct(p) for p in parties]
    if not per_party or not all(per_party):
        return {"kind": "name too generic to look up", "real": None}
    words = [w for ws in per_party for w in ws]
    rows = store().query("CALL db.index.fulltext.queryNodes('case_name', $q) YIELD node, score "
                         "RETURN node.name AS name, node.cite AS cite, node.court AS court, node.year AS year "
                         "LIMIT 50", {"q": " AND ".join(words)})
    same = [h for h in rows if all(w in (h["name"] or "").lower() for w in words)]
    if same:
        real = "; ".join(f"{h['name']}, {h['cite']} ({h['court']} {h['year']})" for h in same[:3])
        return {"kind": "real case, wrong citation", "real": real}
    return {"kind": "no such case in Redline's data", "real": None}


def score_one(path, spec):
    out = SCORES / path.name
    if out.exists():
        return out, "cached"
    from redline.service import check_text
    rec = json.loads(path.read_text())
    brief = rec["answer"] or ""
    chk = check_text(brief)
    cites = [{"text": c["text"], "name": c.get("name"), "verdict": c["verdict"], "status": c["status"],
              "reason": c["reason"], "case": (c.get("case") or {}).get("name")} for c in chk["citations"]]
    # (audit sees the reason too, for short cites that carry no name)
    for c in cites:
        if c["verdict"] == "FABRICATED":
            c["audit"] = audit(c)
    if EXP == "memory":
        rec = {"task": rec["task"], "arm": rec["arm"], "rep": rec["rep"], "summary": chk["summary"],
               "fabricated": [c for c in cites if c["verdict"] == "FABRICATED"],
               "cites_overruled": [c for c in cites if c["status"] in ("overruled", "overruled in part")],
               "citations": cites, "judge": {}, "words": len(brief.split())}
        out.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
        return out, f"fab={rec['summary']['fabricated']}/{rec['summary']['citations']}"
    d = spec["doctrines"][rec["doctrine"]]
    jp = JUDGE.format(name=d["overruled_name"], by=d["overruled_by"], prop=d["overruled_proposition"],
                      today=TODAY, short=d["overruled_name"].split(" v. ")[0], brief=scrub(brief))
    j = claude(jp, JUDGE_MODEL)
    m = re.search(r"\{.*\}", j.get("result", ""), re.S)
    verdict = json.loads(m.group(0)) if m else {"relies": None, "error": j.get("result", "")[:300]}
    rec = {"task": rec["task"], "doctrine": rec["doctrine"], "arm": rec["arm"], "rep": rec["rep"],
           "summary": chk["summary"], "fabricated": [c for c in cites if c["verdict"] == "FABRICATED"],
           "cites_overruled": [c for c in cites if c["status"] in ("overruled", "overruled in part")],
           "citations": cites, "judge": verdict, "judge_model": JUDGE_MODEL, "words": len(brief.split())}
    out.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return out, f"fab={rec['summary']['fabricated']} relies={verdict.get('relies')}"


def score(args):
    spec = load()
    SCORES.mkdir(parents=True, exist_ok=True)
    paths = sorted(RUNS.glob("*.json"))
    with ThreadPoolExecutor(args.jobs) as ex:
        futs = {ex.submit(score_one, p, spec): p.name for p in paths}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                print(f"[{i}/{len(paths)}] {futs[f]}: {f.result()[1]}", flush=True)
            except Exception as e:
                print(f"[{i}/{len(paths)}] {futs[f]}: FAILED {e}", flush=True)


# ---------------------------------------------------------------- report

def sign_test(wins, losses):
    """Two-sided exact sign test: P(as extreme | p = 0.5), ties dropped."""
    n, k = wins + losses, min(wins, losses)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def report(args):
    recs = [json.loads(p.read_text()) for p in sorted(SCORES.glob("*.json"))]
    runs = {p.name: json.loads(p.read_text()) for p in RUNS.glob("*.json")}
    arms = {}
    for a in ARMS:
        rs = [r for r in recs if r["arm"] == a]
        if not rs:
            continue
        n = len(rs)
        cost = [runs.get(f"{r['task']}-{a}-{r['rep']}.json", {}).get("cost_usd") or 0 for r in rs]
        arms[a] = {"runs": n,
                   "relies": sum(bool(r["judge"].get("relies")) for r in rs),
                   "any_fabricated": sum(r["summary"]["fabricated"] > 0 for r in rs),
                   "fabricated_citations": sum(r["summary"]["fabricated"] for r in rs),
                   "citations": sum(r["summary"]["citations"] for r in rs),
                   "verified": sum(r["summary"]["verified"] for r in rs),
                   "unverifiable": sum(r["summary"]["unverifiable"] for r in rs),
                   "cites_overruled_case": sum(bool(r["cites_overruled"]) for r in rs),
                   "judge_unparsed": sum(r["judge"].get("relies") is None for r in rs),
                   "cost_usd": round(sum(cost), 2)}
        arms[a]["either"] = sum(bool(r["judge"].get("relies")) or r["summary"]["fabricated"] > 0 for r in rs)

    def per_task(arm, key):
        t = {}
        for r in recs:
            if r["arm"] == arm:
                bad = bool(r["judge"].get("relies")) if key == "relies" else \
                    r["summary"]["fabricated"] > 0 if key == "fabricated" else \
                    bool(r["judge"].get("relies")) or r["summary"]["fabricated"] > 0
                t[r["task"]] = t.get(r["task"], 0) + bad
        return t

    tests = {}
    for key in ("relies", "fabricated", "either"):
        for x, y in (("A", "C"), ("B", "C"), ("A", "B")):
            tx, ty = per_task(x, key), per_task(y, key)
            common = set(tx) & set(ty)
            w = sum(tx[t] > ty[t] for t in common)
            l = sum(tx[t] < ty[t] for t in common)
            tests[f"{key}:{x}vs{y}"] = {"tasks_worse_in_" + x: w, "tasks_worse_in_" + y: l,
                                        "ties": len(common) - w - l, "p_two_sided": round(sign_test(w, l), 5)}
    by_doctrine = {}
    for r in recs if EXP == "packet" else []:
        b = by_doctrine.setdefault(r["doctrine"], {a: [0, 0] for a in ARMS})
        b[r["arm"]][0] += bool(r["judge"].get("relies"))
        b[r["arm"]][1] += 1
    fabs = [dict(c, task=r["task"], arm=r["arm"], rep=r["rep"]) for r in recs for c in r["fabricated"]]
    for a in arms:
        arms[a]["fabricated_real_case_wrong_cite"] = sum(
            f["audit"]["kind"].startswith("real") for f in fabs if f["arm"] == a)
    summary = {"experiment": EXP, "model": MODEL, "judge_model": JUDGE_MODEL if EXP == "packet" else None,
               "arms": arms, "sign_tests": tests, "relies_by_doctrine": by_doctrine, "fabrications": fabs}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    for a, s in arms.items():
        print(f"{a}: relies {s['relies']}/{s['runs']} ({100*s['relies']/s['runs']:.1f}%), "
              f"any fabricated {s['any_fabricated']}/{s['runs']}, fabricated cites {s['fabricated_citations']}"
              f"/{s['citations']}, unverifiable {s['unverifiable']}, either {s['either']}, ${s['cost_usd']}")
    for k, v in tests.items():
        print(k, v)


KNOW = """Today is {today}. Answer from your own knowledge, with JSON only.

Case: {name}, {cite} ({year}).
Has the US Supreme Court overruled this decision, in whole or in part?

Reply exactly: {{"overruled": true|false, "overruled_by": "<case name, or null>", "confidence": "high"|"medium"|"low"}}"""


def knowledge(args):
    from redline.service import store
    s = store()
    over = s.query("MATCH (a:Case)-[r:OVERRULES]->(b:Case) RETURN b.id AS id, b.name AS name, b.cite AS cite, "
                   "b.year AS year, collect(a.name) AS by, max(r.partial) AS partial")
    ids = {o["id"] for o in over}
    controls = [c for c in s.query(
        "MATCH (c:Case {reporter:'U.S.'}) WHERE c.year >= 1950 AND c.status IS NULL "
        "RETURN c.id AS id, c.name AS name, c.cite AS cite, c.year AS year ORDER BY c.cited_by DESC LIMIT 80")
        if c["id"] not in ids][:60]
    items = [dict(o, truth=True) for o in over] + [dict(c, truth=False, by=[], partial=False) for c in controls]
    path = BASE / "knowledge.json"
    done = {r["id"]: r for r in json.loads(path.read_text())["items"]} if path.exists() else {}

    def ask(it):
        if it["id"] in done and done[it["id"]].get("answer") is not None:
            return done[it["id"]]
        r = claude(KNOW.format(today=TODAY, name=it["name"], cite=it["cite"], year=it["year"]), MODEL)
        m = re.search(r"\{.*\}", r.get("result", ""), re.S)
        try:
            ans = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            ans = None
        return dict(it, answer=ans, raw=r.get("result", "")[:400])

    with ThreadPoolExecutor(args.jobs) as ex:
        out = list(ex.map(ask, items))
    pos = [o for o in out if o["truth"]]
    neg = [o for o in out if not o["truth"]]
    said = lambda o: bool((o["answer"] or {}).get("overruled"))
    missed = [o for o in pos if not said(o)]
    summary = {"model": MODEL, "overruled_cases": len(pos), "model_says_good_law": len(missed),
               "missed_partial": sum(bool(o["partial"]) for o in missed),
               "missed_cited_by_f3d": None, "controls": len(neg),
               "controls_model_says_overruled": sum(said(o) for o in neg),
               "unparsed": sum(o["answer"] is None for o in out)}
    f3d = {r["id"]: r["n"] for r in s.query(
        "MATCH (f:Case {reporter:'F.3d'})-[:CITES]->(o:Case)<-[:OVERRULES]-() RETURN o.id AS id, count(DISTINCT f) AS n")}
    for o in out:
        o["f3d_citing"] = f3d.get(o["id"], 0)
    summary["missed_cited_by_f3d"] = sum(o["f3d_citing"] for o in missed)
    path.write_text(json.dumps({"summary": summary, "items": out}, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    for o in sorted(missed, key=lambda o: -o["f3d_citing"])[:25]:
        print(f"  MISSED {o['name']}, {o['cite']} -> {', '.join(o['by'])} ({o['f3d_citing']} F.3d cases cite it)")
    for o in neg:
        if said(o):
            print(f"  CONTROL said overruled: {o['name']}, {o['cite']} -> {o['answer'].get('overruled_by')}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["packets", "run", "score", "report", "knowledge"])
    p.add_argument("--exp", choices=["memory", "packet"], default="memory")
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--only", nargs="*")
    p.add_argument("--arms", nargs="*")
    a = p.parse_args()
    use(a.exp)
    {"knowledge": lambda: knowledge(a), "packets": lambda: packets(), "run": lambda: run(a), "score": lambda: score(a),
     "report": lambda: report(a)}[a.cmd]()


if __name__ == "__main__":
    sys.exit(main())
