"""Redline on citations that US courts found fabricated, from the AI Hallucination Cases database
(Damien Charlotin, CC BY 4.0).

Each case lists its hallucinations as items such as "Fabricated: Case Law | Counsel cited Hinkle v.
CBE Grp., 827 F.3d 129 (5th Cir. 2016); ...". For every "Fabricated: Case Law" item in a US case, the
first citation the item quotes is the one the court could not find. Redline checks it with the item's
own wording around it, so the cited case name is read the same way it would be in a brief.

    python bench/wild.py      # downloads the CSV once -> bench/results/wild.json
"""
import collections
import csv
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from redline.store import Store  # noqa: E402
from redline.verify import check  # noqa: E402

CSV = ROOT / "data" / "raw" / "charlotin" / "hallucinations.csv"
URL = "https://www.damiencharlotin.com/hallucinations/hallucinations/download.csv"
OUT = ROOT / "bench" / "results" / "wild.json"
HELD = {"U.S.", "F.3d"}


def load():
    if not CSV.exists():
        CSV.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": "redline-bench/0.1"})
        CSV.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return list(csv.DictReader(CSV.open(encoding="utf-8", errors="replace")))


def main():
    store = Store()
    rows = [r for r in load() if "USA" in (r.get("State(s)") or "")]
    results, verdicts = [], collections.Counter()
    for r in rows:
        for item in (r.get("Hallucination Items") or "").split("||"):
            label, _, text = item.partition("|")
            if label.strip() != "Fabricated: Case Law":
                continue
            found = check(store, text)["citations"]
            if not found:
                continue
            c = found[0]
            in_scope = c["reporter"] in HELD or c.get("problem") in ("no_such_series", "series_not_in_print")
            if not in_scope:
                continue
            verdicts[c["verdict"]] += 1
            results.append({"case": r["Case Name"], "date": r["Date"], "court": r["Court"], "citation": c["text"],
                            "verdict": c["verdict"], "problem": c.get("problem"), "reason": c["reason"],
                            "item": " ".join(text.split())[:400]})
    total = sum(verdicts.values())
    out = {"source": "AI Hallucination Cases database, Damien Charlotin (CC BY 4.0)", "us_cases": len(rows),
           "fabricated_citations_in_scope": total, "verdicts": dict(verdicts),
           "proved_fabricated": verdicts["FABRICATED"], "results": results}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"{len(rows)} US cases; {total} court-identified fabricated citations in U.S., F.3d or impossible series")
    print(f"Redline: {dict(verdicts)}")
    return out


if __name__ == "__main__":
    main()
