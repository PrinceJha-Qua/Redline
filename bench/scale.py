"""Measure a Redline store: size, counts, and how fast the multi-hop questions answer.

    python bench/scale.py                       # the core store
    python bench/scale.py data/packs/redline-federal.rl
"""
import statistics
import sys
import time
from pathlib import Path

import relate

ROOT = Path(__file__).resolve().parents[1]
CHEVRON = "US:467:837"
RUNS = 20

# Each hop starts from the anchored case and walks citations backwards, one distinct frontier at a time.
RESTS_ON = {
    1: "MATCH (t:Case {id: $id})<-[:CITES]-(a:Case) RETURN count(DISTINCT a) AS n",
    2: "MATCH (t:Case {id: $id})<-[:CITES]-(m:Case) WITH DISTINCT m "
       "MATCH (m)<-[:CITES]-(a:Case) RETURN count(DISTINCT a) AS n",
    3: "MATCH (t:Case {id: $id})<-[:CITES]-(m:Case) WITH DISTINCT m "
       "MATCH (m)<-[:CITES]-(n:Case) WITH DISTINCT n "
       "MATCH (n)<-[:CITES]-(a:Case) RETURN count(DISTINCT a) AS n",
}
APPEALS_ON_OVERRULED = {
    1: "MATCH (o:Case {status: 'overruled'})<-[:CITES]-(a:Case {reporter: 'F.3d'}) RETURN count(DISTINCT a) AS n",
    2: "MATCH (o:Case {status: 'overruled'})<-[:CITES]-(m:Case) WITH DISTINCT m "
       "MATCH (m)<-[:CITES]-(a:Case {reporter: 'F.3d'}) RETURN count(DISTINCT a) AS n",
}


def main(path):
    path = Path(path)
    con = relate.connect(str(path), read_only=True)
    cur = con.cursor()

    def one(query, params=None):
        start = time.perf_counter()
        cur.execute(query, params or {})
        rows = cur.fetchall()
        return rows, (time.perf_counter() - start) * 1000

    size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
    print(f"store      {path}  {size / 1e6:.1f} MB")
    for label, n in sorted((r["l"], r["n"]) for r in one("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS n")[0]):
        print(f"  node     {label:<10} {n:>10,}")
    for kind, n in sorted((r["t"], r["n"]) for r in one("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n")[0]):
        print(f"  rel      {kind:<12} {n:>10,}")

    print(f"\ncases resting on Chevron ({CHEVRON}), {RUNS} runs each")
    print("  hops      cases   median ms    worst ms")
    for hops, query in RESTS_ON.items():
        times, n = [], 0
        for _ in range(RUNS):
            rows, ms = one(query, {"id": CHEVRON})
            times.append(ms)
            n = rows[0]["n"]
        print(f"  {hops}    {n:>10,}  {statistics.median(times):>10.1f}  {max(times):>10.1f}")

    print("\nappeals-court cases resting on any overruled Supreme Court case")
    for hops, query in APPEALS_ON_OVERRULED.items():
        rows, ms = one(query)
        print(f"  {hops} hop(s)  {rows[0]['n']:>10,}   {ms:.0f} ms")
    con.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "redline-us")
