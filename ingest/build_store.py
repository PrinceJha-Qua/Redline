"""Build a Redline store: one Relate file holding reporters, volumes, cases and what cites what.

    python -m ingest.build_store                    # core store   -> data/redline-us/
    python -m ingest.build_store --pack federal     # federal pack -> data/packs/redline-federal/

Stores are written as Relate directory stores. A single .rl file of the same graph is about eight
times larger, because it keeps the space its write log and earlier snapshots once used.
`relate clone data/redline-us data/redline-us.rl` writes a compact single file from it.

Graph
    (:Reporter)-[:HAS_VOLUME]->(:Volume)-[:CONTAINS]->(:Case)-[:DECIDED_BY]->(:Court)
    (:Case)-[:CITES {weight, parenthetical}]->(:Case)
    (:Case)-[:OVERRULES {partial, topic, source}]->(:Case)
    (:Citation {text})-[:CITATION_OF]->(:Case)       parallel citations (S. Ct., L. Ed.)

The core store carries every case's page range for both reporters, the Supreme Court citation
network, and each appeals-court citation to a Supreme Court case. The federal pack adds the
citations between appeals-court cases.
"""
import argparse
import json
import re
import shutil
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import relate

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "cap"
OVERRULINGS = ROOT / "data" / "overrulings.json"
AUDIT = ROOT / "data" / "pagemap_audit.json"  # from bench/pagemap_audit.py
UNTRUSTED_AT = 2       # court-cited start pages that fall inside another case before a volume is untrusted
UNTRUSTED_ORPHANS = 10  # court-cited start pages with no case at all: the volume is missing cases

REPORTERS = {
    # min_words: U.S. Reports volumes list thousands of one-line orders ("certiorari denied").
    # Those are kept as order pages on the volume, not as cases.
    "us": {"abbr": "U.S.", "prefix": "US", "name": "United States Reports", "min_words": 300, "level": "supreme"},
    "f3d": {"abbr": "F.3d", "prefix": "F3d", "name": "Federal Reporter, Third Series", "min_words": 0, "level": "appeals"},
}
PACKS = {
    # parens: which citations keep the court's parenthetical, e.g. "(deferring to the agency's reading)".
    "core": {"out": ROOT / "data" / "redline-us", "edges": {("us", "us"), ("f3d", "us")},
             "parens": {("us", "us"), ("f3d", "us")}},
    "federal": {"out": ROOT / "data" / "packs" / "redline-federal",
                "edges": {("us", "us"), ("f3d", "us"), ("f3d", "f3d"), ("us", "f3d")},
                "parens": {("us", "us"), ("f3d", "us"), ("f3d", "f3d"), ("us", "f3d")}},
}
BATCH = 5000
PAREN_MAX = 200


def _page(text, last=False):
    nums = re.findall(r"\d+", str(text or ""))
    return int(nums[-1 if last else 0]) if nums else None


def _clean_cite(text):
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("U. S.", "U.S.").replace("S. Ct.", "S.Ct.").replace("L. Ed.", "L.Ed.")


def read_reporter(slug):
    """Return (cases, volumes, raw citation lists) for one reporter, reading one volume at a time."""
    spec = REPORTERS[slug]
    cases, volumes, raw_cites = {}, {}, {}
    files = sorted((RAW / slug).glob("[0-9]*.json"), key=lambda p: int(p.stem))
    for path in files:
        vol = int(path.stem)
        records = json.loads(path.read_text())
        v = {"key": f"{spec['prefix']}:{vol}", "reporter": spec["abbr"], "vol": vol, "first_page": None,
             "last_page": 0, "cases": 0, "order_pages": set(), "first_year": 9999, "last_year": 0}
        by_page = defaultdict(list)
        for r in records:
            first, last = _page(r.get("first_page")), _page(r.get("last_page"), last=True)
            if first is None:
                continue
            last = max(last or first, first)
            v["first_page"] = first if v["first_page"] is None else min(v["first_page"], first)
            v["last_page"] = max(v["last_page"], last)
            year = int((r.get("decision_date") or "0")[:4] or 0)
            if year:
                v["first_year"], v["last_year"] = min(v["first_year"], year), max(v["last_year"], year)
            words = (r.get("analysis") or {}).get("word_count") or 0
            if words < spec["min_words"]:
                v["order_pages"].update(range(first, last + 1))
                continue
            by_page[first].append((words, r, last, year))
        for first, group in by_page.items():
            group.sort(key=lambda g: -g[0])  # the longest opinion on a page owns the plain id
            for n, (words, r, last, year) in enumerate(group):
                cid = f"{spec['prefix']}:{vol}:{first}" + (f".{n + 1}" if n else "")
                court = r.get("court") or {}
                cites = [_clean_cite(c["cite"]) for c in r.get("citations") or [] if c.get("type") in ("official", "parallel")]
                official = f"{vol} {spec['abbr']} {first}"
                cases[r["id"]] = {
                    "id": cid, "name": (r.get("name_abbreviation") or r.get("name") or "")[:160], "cite": official,
                    # the full caption names every party: co-defendants and relators the short name drops
                    "title": re.sub(r"\s+", " ", r.get("name") or "")[:300],
                    "reporter": spec["abbr"], "vol": vol, "first_page": first, "last_page": last,
                    "date": r.get("decision_date") or "", "year": year, "court": court.get("name_abbreviation") or "",
                    "court_name": court.get("name") or "", "words": words, "vkey": v["key"],
                    "parallel": sorted({c for c in cites if c != official and spec["abbr"] not in c}),
                }
                raw_cites[r["id"]] = [(t.get("case_ids") or [], t.get("weight") or 1,
                                       next((p["parenthetical"] for p in t.get("pin_cites") or [] if p.get("parenthetical")), ""))
                                      for t in r.get("cites_to") or [] if t.get("case_ids")]
                v["cases"] += 1
        v["order_pages"] = sorted(v["order_pages"])
        volumes[v["key"]] = v
    return cases, volumes, raw_cites


def hits(nodes, edges, rounds=30):
    """Authority and hub scores (Kleinberg), as Fowler and Jeon applied them to Supreme Court precedent."""
    out_, in_ = defaultdict(list), defaultdict(list)
    for s, t in edges:
        out_[s].append(t)
        in_[t].append(s)
    hub = dict.fromkeys(nodes, 1.0)
    auth = dict.fromkeys(nodes, 0.0)
    for _ in range(rounds):
        for n in in_:
            auth[n] = sum(hub[s] for s in in_[n])
        top = max(auth.values()) or 1.0
        for n in in_:
            auth[n] /= top
        for n in out_:
            hub[n] = sum(auth[t] for t in out_[n])
        top = max((hub[n] for n in out_), default=1.0) or 1.0
        for n in nodes:
            hub[n] = hub[n] / top if n in out_ else 0.0
    return auth, hub, {n: len(v) for n, v in in_.items()}


def _size(path):
    """Bytes on disk: a single .rl file, or every file in a directory store."""
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return path.stat().st_size


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


def add_indexes(run):
    """Full-text indexes: case names, and the parentheticals courts write about the cases they cite
    ("holding that temporal proximity alone is insufficient"), which an agent searches for authority."""
    run("CREATE FULLTEXT INDEX case_name IF NOT EXISTS FOR (c:Case) ON EACH [c.name]")
    run("CREATE FULLTEXT INDEX cites_parenthetical IF NOT EXISTS FOR ()-[r:CITES]-() ON EACH [r.parenthetical]")


def build(pack="core", out=None, reporters=("us", "f3d")):
    spec = PACKS[pack]
    out = Path(out).resolve() if out else spec["out"]
    t0 = time.time()

    cases, volumes, slug_of, raw = {}, {}, {}, {}
    for slug in reporters:
        c, v, rc = read_reporter(slug)
        cases.update(c)
        volumes.update(v)
        raw.update(rc)
        slug_of.update(dict.fromkeys(c, slug))
        print(f"  read {slug}: {len(c):,} cases in {len(v):,} volumes ({time.time() - t0:.0f}s)", flush=True)

    edges = {}
    for src, cites in raw.items():
        s = cases[src]["id"]
        for ids, weight, paren in cites:
            for tid in ids:
                if tid not in cases or tid == src or (slug_of[src], slug_of[tid]) not in spec["edges"]:
                    continue
                e = edges.setdefault((s, cases[tid]["id"]), [0, ""])
                e[0] += weight
                if (slug_of[src], slug_of[tid]) in spec["parens"]:
                    e[1] = e[1] or paren[:PAREN_MAX]
    del raw
    print(f"  {len(edges):,} citations ({time.time() - t0:.0f}s)", flush=True)

    by_id = {c["id"]: c for c in cases.values()}
    overrulings, source = [], ""
    if OVERRULINGS.exists():
        data = json.loads(OVERRULINGS.read_text())
        source = data["source"]
        for row in data["rows"]:
            pair = []
            for d in (row["overruling"], row["overruled"]):
                cid = f"US:{d['vol']}:{d['page']}" if d["page"] else f"US:{d['vol']}:slip:{_slug(d['name'])}"
                if cid not in by_id:  # decided after CAP's last volume (Dobbs, Loper Bright): name and citation only
                    by_id[cid] = {"id": cid, "name": d["name"], "cite": f"{d['vol']} U.S. {d['page'] or '___'}",
                                  "reporter": "U.S.", "vol": d["vol"], "first_page": d["page"] or 0,
                                  "last_page": d["page"] or 0, "date": "", "year": d["year"], "court": "U.S.",
                                  "court_name": "Supreme Court of the United States", "words": 0, "vkey": None,
                                  "parallel": [], "stub": True}
                pair.append(cid)
            overrulings.append({"s": pair[0], "t": pair[1], "partial": row["partial"], "topic": row["topic"], "source": source})
    status = {}
    for o in overrulings:
        if status.get(o["t"]) != "overruled":
            status[o["t"]] = "overruled in part" if o["partial"] else "overruled"

    auth, hub, cited_by = hits(list(by_id), list(edges))
    print(f"  scores done ({time.time() - t0:.0f}s)", flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.is_dir():
        shutil.rmtree(out)
    elif out.exists():
        out.unlink()
    db = relate.Database(str(out))

    def run(query, rows=None):
        if rows is None:
            db.execute(query, {})
            return
        for i in range(0, len(rows), BATCH):
            db.execute(query, {"rows": rows[i:i + BATCH]})

    for q in ("CREATE CONSTRAINT case_id IF NOT EXISTS FOR (c:Case) REQUIRE c.id IS UNIQUE",
              "CREATE CONSTRAINT volume_key IF NOT EXISTS FOR (v:Volume) REQUIRE v.key IS UNIQUE",
              "CREATE CONSTRAINT reporter_abbr IF NOT EXISTS FOR (r:Reporter) REQUIRE r.abbr IS UNIQUE",
              "CREATE CONSTRAINT court_id IF NOT EXISTS FOR (k:Court) REQUIRE k.id IS UNIQUE",
              "CREATE CONSTRAINT citation_text IF NOT EXISTS FOR (x:Citation) REQUIRE x.text IS UNIQUE",
              "CREATE INDEX case_status IF NOT EXISTS FOR (c:Case) ON (c.status)"):
        run(q)

    rep_rows = []
    for slug in reporters:
        r = REPORTERS[slug]
        vs = [v for v in volumes.values() if v["reporter"] == r["abbr"]]
        rep_rows.append({"abbr": r["abbr"], "name": r["name"], "first_vol": min(v["vol"] for v in vs),
                         "last_vol": max(v["vol"] for v in vs), "volumes": len(vs),
                         "first_year": min(v["first_year"] for v in vs), "last_year": max(v["last_year"] for v in vs),
                         "complete": True, "source": "Caselaw Access Project, Harvard Law School Library"})
    run("UNWIND $rows AS r CREATE (x:Reporter) SET x = r", rep_rows)
    audit = json.loads(AUDIT.read_text())["volumes"] if AUDIT.exists() else {}
    if not audit:
        print("  no page-map audit found: run `python bench/pagemap_audit.py` first; every volume is untrusted")

    def _volume_row(v):
        orphans = audit.get(v["key"], [])
        return {"key": v["key"], "reporter": v["reporter"], "vol": v["vol"], "first_page": v["first_page"] or 0,
                "last_page": v["last_page"], "cases": v["cases"], "order_pages": v["order_pages"],
                # pages courts cite as a case's start where the data has none: never called fabricated
                "cited_starts": sorted(o["page"] for o in orphans),
                # complete: the page map agrees with how courts cite this volume, so it can prove a fake
                "complete": bool(audit) and sum(1 for o in orphans if o["inside"]) < UNTRUSTED_AT
                            and len(orphans) < UNTRUSTED_ORPHANS}

    run("UNWIND $rows AS r CREATE (v:Volume) SET v = r", [_volume_row(v) for v in volumes.values()])
    run("UNWIND $rows AS r MATCH (x:Reporter {abbr: r.reporter}), (v:Volume {key: r.key}) CREATE (x)-[:HAS_VOLUME]->(v)",
        [{"reporter": v["reporter"], "key": v["key"]} for v in volumes.values()])

    courts = {}
    for c in by_id.values():
        if c["court"]:
            level = "supreme" if c["court"] == "U.S." else "appeals"
            courts.setdefault(c["court"], {"id": c["court"], "name": c["court_name"] or c["court"], "level": level})
    run("UNWIND $rows AS r CREATE (k:Court) SET k = r", list(courts.values()))

    case_rows = []
    for c in by_id.values():
        row = {k: c[k] for k in ("id", "name", "cite", "reporter", "vol", "first_page", "last_page", "date", "year", "court")}
        if c.get("title") and c["title"].lower() != c["name"].lower():
            row["title"] = c["title"]
        row["authority"] = round(auth.get(c["id"], 0.0), 4)
        row["cited_by"] = cited_by.get(c["id"], 0)
        if c["id"] in status:
            row["status"] = status[c["id"]]
        if c.get("stub"):
            row["stub"] = True
        case_rows.append(row)
    run("UNWIND $rows AS r CREATE (c:Case) SET c = r", case_rows)
    print(f"  wrote {len(case_rows):,} cases ({time.time() - t0:.0f}s)", flush=True)
    run("UNWIND $rows AS r MATCH (v:Volume {key: r.v}), (c:Case {id: r.c}) CREATE (v)-[:CONTAINS]->(c)",
        [{"v": c["vkey"], "c": c["id"]} for c in by_id.values() if c["vkey"]])
    run("UNWIND $rows AS r MATCH (c:Case {id: r.c}), (k:Court {id: r.k}) CREATE (c)-[:DECIDED_BY]->(k)",
        [{"c": c["id"], "k": c["court"]} for c in by_id.values() if c["court"]])
    par = defaultdict(list)
    for c in by_id.values():
        for text in c["parallel"]:
            par[text].append(c["id"])
    run("UNWIND $rows AS r CREATE (x:Citation {text: r.text})", [{"text": t} for t in par])
    run("UNWIND $rows AS r MATCH (x:Citation {text: r.text}), (c:Case {id: r.c}) CREATE (x)-[:CITATION_OF]->(c)",
        [{"text": t, "c": cid} for t, ids in par.items() for cid in ids])
    print(f"  wrote structure ({time.time() - t0:.0f}s)", flush=True)

    plain = [{"s": s, "t": t, "w": w} for (s, t), (w, p) in edges.items() if not p]
    noted = [{"s": s, "t": t, "w": w, "p": p} for (s, t), (w, p) in edges.items() if p]
    run("UNWIND $rows AS r MATCH (a:Case {id: r.s}), (b:Case {id: r.t}) CREATE (a)-[:CITES {weight: r.w}]->(b)", plain)
    run("UNWIND $rows AS r MATCH (a:Case {id: r.s}), (b:Case {id: r.t}) "
        "CREATE (a)-[:CITES {weight: r.w, parenthetical: r.p}]->(b)", noted)
    run("UNWIND $rows AS r MATCH (a:Case {id: r.s}), (b:Case {id: r.t}) "
        "CREATE (a)-[:OVERRULES {partial: r.partial, topic: r.topic, source: r.source}]->(b)", overrulings)
    print(f"  wrote {len(edges):,} citations, {len(overrulings)} overrulings ({time.time() - t0:.0f}s)", flush=True)

    add_indexes(run)
    db.execute("CREATE (m:Meta) SET m = $m", {"m": {
        "pack": pack, "built": date.today().isoformat(), "cases": len(case_rows), "citations": len(edges),
        "overrulings": len(overrulings), "volumes": len(volumes),
        "sources": ["Caselaw Access Project, Harvard Law School Library (static.case.law)", source]}})
    db.flush()
    db.close()
    size = _size(out) / 1e6
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"{shown}: {len(case_rows):,} cases, {len(edges):,} citations, "
          f"{len(overrulings)} overrulings, {size:.1f} MB, built in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", choices=PACKS, default="core")
    ap.add_argument("--out")
    ap.add_argument("--reporters", default="us,f3d")
    a = ap.parse_args()
    build(a.pack, a.out, tuple(a.reporters.split(",")))
