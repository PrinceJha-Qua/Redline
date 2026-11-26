"""Redline on citations that US courts found fabricated, from the AI Hallucination Cases database
(Damien Charlotin, CC BY 4.0).

Each case lists its hallucinations as items such as "Fabricated: Case Law | Counsel cited Hinkle v.
CBE Grp., 827 F.3d 129 (5th Cir. 2016); ...". For every "Fabricated: Case Law" item in a US case, the
first citation the item quotes is the one the court could not find. Redline checks it with the item's
own wording around it, so the cited case name is read the same way it would be in a brief.

    python bench/wild.py          # downloads the CSV once -> bench/results/wild.json
    python bench/wild.py replay   # -> web/data/replay.json, the page at /replay
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




REPLAY = ROOT / "web" / "data" / "replay.json"


def replay():
    """The sanctions cases, one filing at a time: what Redline would have said before the brief was
    filed, with the repair it suggests. Re-checked with the current code from the stored item text."""
    from redline.agent import did_you_mean
    data = json.loads(OUT.read_text())
    store = Store()
    filings, changed = {}, 0
    for r in data["results"]:
        c = check(store, r["item"])["citations"][0]
        changed += c["verdict"] != r["verdict"]
        fix = did_you_mean(store, c["name"]) if c["verdict"] == "FABRICATED" and c.get("name") else []
        f = filings.setdefault((r["case"], r["court"], r["date"]), {
            "case": r["case"], "court": r["court"], "date": r["date"], "citations": []})
        f["citations"].append({"citation": c["text"], "name": c.get("name"), "verdict": c["verdict"],
                               "reason": c["reason"], "court_said": r["item"],
                               "suggestion": [{"name": s["name"], "cite": s["cite"], "court": s["court"],
                                               "year": s["year"]} for s in fix[:3]]})
    rows = sorted(filings.values(), key=lambda f: f["date"], reverse=True)
    for f in rows:
        f["caught"] = any(c["verdict"] == "FABRICATED" for c in f["citations"])
    # Where the court named the case the lawyer meant, did Redline suggest that case?
    named = [c for f in rows for c in f["citations"] if c["suggestion"]]
    agree = [c for c in named if any(s["cite"] in c["court_said"] for s in c["suggestion"])]
    out = {"source": data["source"], "filings": len(rows), "caught": sum(f["caught"] for f in rows),
           "citations": sum(len(f["citations"]) for f in rows),
           "verdicts": dict(collections.Counter(c["verdict"] for f in rows for c in f["citations"])),
           "suggestions": len(named), "suggestion_matches_court": len(agree),
           "changed_since_benchmark": changed, "rows": rows}
    REPLAY.parent.mkdir(parents=True, exist_ok=True)
    REPLAY.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"{out['caught']} of {out['filings']} sanctioned filings caught; verdicts {out['verdicts']}; "
          f"{len(named)} repairs suggested, {len(agree)} name the citation the court gave; "
          f"{changed} verdicts differ from wild.json")
    return out


if __name__ == "__main__":
    replay() if sys.argv[1:] == ["replay"] else main()
