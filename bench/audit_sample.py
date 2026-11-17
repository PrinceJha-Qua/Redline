"""Draw the hand-audit sample: 150 Redline verdicts on real opinions, for a person to judge.

The sample is stratified so rare verdicts are audited too: every FABRICATED verdict from the
false-alarm run, then caution, overruled, good-law and unverifiable verdicts. A person fills in the
last three columns of bench/audit.csv; bench/report.py summarises whatever has been judged.

    python bench/audit_sample.py      # needs bench/results/false_alarms.json's opinions downloaded
"""
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))
import false_alarms  # noqa: E402
from redline.store import Store  # noqa: E402
from redline.verify import check  # noqa: E402

OUT = ROOT / "bench" / "audit.csv"
QUOTA = {"FABRICATED": 30, "caution": 30, "overruled": 20, "good law": 40, "UNVERIFIABLE": 30}
SEED = 7


def bucket(c):
    if c["verdict"] != "VERIFIED":
        return c["verdict"]
    return "overruled" if (c["status"] or "").startswith("overruled") else c["status"]


def main():
    if OUT.exists():
        sys.exit(f"{OUT} exists; it may hold judgements. Move it away to draw a new sample.")
    store, rng = Store(), random.Random(SEED)
    pools = {k: [] for k in QUOTA}
    for item in false_alarms.pick():
        text = false_alarms.fetch(item)
        for c in check(store, text)["citations"]:
            b = bucket(c)
            if b in pools:
                a, z = c["span"]
                pools[b].append({"opinion": f"{item[3]} ({item[0]} {item[1]}, {item[2]})", "citation": c["text"],
                                 "verdict": c["verdict"], "status": c["status"] or "", "reason": c["reason"],
                                 "context": " ".join(text[max(0, a - 200):z + 80].split())})
    rows = []
    for b, n in QUOTA.items():
        rows += rng.sample(pools[b], min(n, len(pools[b])))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "opinion", "citation", "verdict", "status", "reason", "context",
                                          "auditor_agrees", "correct_verdict", "notes"])
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"id": i, **r, "auditor_agrees": "", "correct_verdict": "", "notes": ""})
    print(f"{len(rows)} verdicts -> {OUT}. Fill in auditor_agrees (yes/no), correct_verdict and notes.")


if __name__ == "__main__":
    main()
