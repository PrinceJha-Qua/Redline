"""How often does Redline call a real citation fabricated?

Takes a fixed random sample of published opinions from the Caselaw Access Project, checks every
citation the judges wrote, and lists every FABRICATED verdict for review. Citations in published
opinions are real, so each one is a false alarm unless the opinion's own text is wrong (an OCR error
or a typo by the court), which the review records.

    python bench/false_alarms.py            # 400 F.3d + 100 U.S. opinions -> bench/results/false_alarms.json
    python bench/false_alarms.py --holdout  # a different 500, never used to tune Redline
"""
import collections
import json
import random
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from redline.store import Store  # noqa: E402
from redline.verify import check  # noqa: E402

RAW = ROOT / "data" / "raw" / "cap"
TEXT = ROOT / "data" / "raw" / "cap-text"
HOLDOUT = "--holdout" in sys.argv  # a second sample with another seed, never used to tune Redline
OUT = ROOT / "bench" / "results" / ("false_alarms-holdout.json" if HOLDOUT else "false_alarms.json")
TEXT_ERRORS = {e["citation"]: e["evidence"]
               for e in json.loads((ROOT / "bench" / "text_errors.json").read_text())["errors"]}
SAMPLE = {"f3d": 400, "us": 100}
SEED = 20261118 if HOLDOUT else 20261117
MIN_WORDS = 1500  # opinions long enough to cite things


def pick():
    rng = random.Random(SEED)
    chosen = []
    for slug, n in SAMPLE.items():
        pool = []
        for f in sorted((RAW / slug).glob("[0-9]*.json"), key=lambda p: int(p.stem)):
            for r in json.loads(f.read_text()):
                if (r.get("analysis") or {}).get("word_count", 0) >= MIN_WORDS and (slug != "us" or r["decision_date"] >= "1990"):
                    pool.append((slug, f.stem, r["file_name"], r["name_abbreviation"]))
        chosen += rng.sample(pool, n)
    if HOLDOUT:  # disjoint from the tuning sample
        tuned = set(pick_seed(20261117))
        chosen = [c for c in chosen if c not in tuned]
    return chosen


def pick_seed(seed):
    rng, out = random.Random(seed), []
    for slug, n in SAMPLE.items():
        pool = []
        for f in sorted((RAW / slug).glob("[0-9]*.json"), key=lambda p: int(p.stem)):
            for r in json.loads(f.read_text()):
                if (r.get("analysis") or {}).get("word_count", 0) >= MIN_WORDS and (slug != "us" or r["decision_date"] >= "1990"):
                    pool.append((slug, f.stem, r["file_name"], r["name_abbreviation"]))
        out += rng.sample(pool, n)
    return out


def fetch(item):
    slug, vol, name, _ = item
    path = TEXT / slug / vol / f"{name}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://static.case.law/{slug}/{vol}/cases/{name}.json"
        body = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "redline-bench/0.1"}), timeout=120).read()
        path.write_bytes(body)
    case = json.loads(path.read_text())
    return "\n\n".join(o.get("text", "") for o in case.get("casebody", {}).get("opinions", []))


def main():
    items = pick()
    with ThreadPoolExecutor(8) as pool:
        texts = list(pool.map(fetch, items))
    store = Store()
    verdicts, problems = collections.Counter(), collections.Counter()
    flagged = []
    started = time.perf_counter()
    for (slug, vol, name, title), text in zip(items, texts):
        result = check(store, text)
        for c in result["citations"]:
            verdicts[c["verdict"]] += 1
            if c["verdict"] == "FABRICATED":
                problems[c.get("problem")] += 1
                a, b = c["span"]
                flagged.append({"opinion": f"{title}, {vol} {'F.3d' if slug == 'f3d' else 'U.S.'} ({name})",
                                "citation": c["text"], "problem": c.get("problem"), "reason": c["reason"],
                                "context": " ".join(text[max(0, a - 160):b + 60].split())})
    seconds = time.perf_counter() - started
    total = sum(verdicts.values())
    for f in flagged:
        f["text_error"] = TEXT_ERRORS.get(f["citation"])
    text_errors = sum(1 for f in flagged if f["text_error"])
    redline_errors = len(flagged) - text_errors
    out = {"sample": SAMPLE, "seed": SEED, "opinions": len(items), "citations": total, "verdicts": dict(verdicts),
           "fabricated": len(flagged), "fabricated_rate": round(len(flagged) / total, 5) if total else None,
           "by_problem": dict(problems), "text_errors": text_errors, "redline_errors": redline_errors,
           "redline_error_rate": round(redline_errors / total, 6) if total else None,
           "seconds": round(seconds, 1), "flagged": flagged}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"{len(items)} opinions, {total:,} citations checked in {seconds:.0f}s: {dict(verdicts)}")
    print(f"called fabricated: {len(flagged)} ({out['fabricated_rate']:.3%}) {dict(problems)}")
    print(f"  errors in the opinion text itself (OCR or typo, confirmed): {text_errors}")
    print(f"  Redline errors: {redline_errors} ({out['redline_error_rate']:.4%} of citations)")
    return out


if __name__ == "__main__":
    main()
