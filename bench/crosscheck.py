"""An independent second implementation, checked against the Cypher Redline runs.

Redline's verdicts rest on two graph answers: which case owns a page of a volume (fabrication), and
which cases cite a case that was later overruled (caution). This script reads the Relate store's
Parquet files directly, with pyarrow and plain Python, no Relate and no Cypher, computes both answers
itself, and compares them with the queries in redline/verify.py and redline/status.py.

    pip install pyarrow && python bench/crosscheck.py     # -> bench/results/crosscheck.json
"""
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from redline.status import STANDS_ON  # noqa: E402
from redline.store import Store, store_path  # noqa: E402
from redline.verify import _AT_PAGE  # noqa: E402

OUT = ROOT / "bench" / "results" / "crosscheck.json"
RANDOM_PAGES = 40  # per volume, on top of every case's first and last page


def _prop(row, name):
    v = row.get(f"p_{name}")
    if v is not None:
        return v
    props = json.loads(row.get("properties") or "{}")
    return (props.get(name) or {}).get("v")


def read_store(path):
    manifest = json.loads((path / "manifest.json").read_text())
    nodes, rels = {}, []
    for part in manifest["node_parts"]:
        for row in pq.read_table(path / part["path"]).to_pylist():
            nodes[row["id"]] = row
    for part in manifest["rel_parts"]:
        t = pq.read_table(path / part["path"], columns=["start_id", "end_id", "type", "properties"])
        rels.extend(t.to_pylist())
    return nodes, rels


def main():
    t0 = time.time()
    path = store_path()
    nodes, rels = read_store(path)
    case = {i: n for i, n in nodes.items() if "Case" in (n["labels"] or [])}
    volume = {i: _prop(n, "key") for i, n in nodes.items() if "Volume" in (n["labels"] or [])}
    contains = defaultdict(list)
    cites, overrules = defaultdict(list), defaultdict(list)
    for r in rels:
        if r["type"] == "CONTAINS" and r["start_id"] in volume:
            contains[volume[r["start_id"]]].append(case[r["end_id"]])
        elif r["type"] == "CITES":
            cites[r["end_id"]].append(r["start_id"])
        elif r["type"] == "OVERRULES":
            overrules[r["end_id"]].append(r["start_id"])
    print(f"read {len(nodes):,} nodes and {len(rels):,} relationships from Parquet in {time.time() - t0:.1f}s")

    store = Store(path)
    rnd = random.Random(2026)
    pages_checked, page_mismatch = 0, []
    for key, cs in sorted(contains.items()):
        last = max(c["p_last_page"] for c in cs)
        probe = {c["p_first_page"] for c in cs} | {c["p_last_page"] for c in cs} | \
                {rnd.randint(1, last + 25) for _ in range(RANDOM_PAGES)}
        for page in sorted(probe):
            mine = sorted(c["p_id"] for c in cs if c["p_first_page"] <= page <= c["p_last_page"])
            theirs = sorted(r["id"] for r in store.query(_AT_PAGE, {"key": key, "page": page}))
            pages_checked += 1
            if mine != theirs:
                page_mismatch.append({"volume": key, "page": page, "parquet": mine, "cypher": theirs})
    print(f"page ownership: {pages_checked:,} lookups, {len(page_mismatch)} disagreements")

    # Caution: for every overruled case, the cases citing it that were decided no later than the
    # overruling (by a case other than themselves), computed from edge rows.
    chains_checked, chain_mismatch = 0, []
    overruled = {o: by for o, by in overrules.items() if _prop(case[o], "status") is not None}
    citers = {c for o in overruled for c in cites[o]}
    for c in sorted(citers, key=lambda i: case[i]["p_id"]):
        cid, year = case[c]["p_id"], case[c]["p_year"] or 0
        mine = sorted({(case[o]["p_id"], case[b]["p_id"]) for o, bys in overruled.items() if c in cites[o]
                       for b in bys if (case[b]["p_year"] or 0) >= year and b != c})
        theirs = sorted({(r["id"], r["by_id"]) for r in store.query(STANDS_ON, {"id": cid})})
        chains_checked += 1
        if mine != theirs:
            chain_mismatch.append({"case": cid, "parquet": mine, "cypher": theirs})
    print(f"stands-on chains: {chains_checked:,} citing cases, {len(chain_mismatch)} disagreements")

    out = {"store": str(path.relative_to(ROOT)), "nodes": len(nodes), "relationships": len(rels),
           "page_lookups": pages_checked, "page_disagreements": page_mismatch[:50],
           "chain_cases": chains_checked, "chain_disagreements": chain_mismatch[:50],
           "agree": not page_mismatch and not chain_mismatch, "seconds": round(time.time() - t0, 1)}
    OUT.write_text(json.dumps(out, indent=2))
    print("AGREE" if out["agree"] else "DISAGREE", f"({out['seconds']}s) -> {OUT.relative_to(ROOT)}")
    return 0 if out["agree"] else 1


if __name__ == "__main__":
    sys.exit(main())
