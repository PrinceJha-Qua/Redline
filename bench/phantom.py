"""Redline on LePhantomCite (Liu, Stammbach & Henderson 2026, CC BY 4.0): 390 excerpts from federal
appellate briefs and model-written holdings, with citation errors injected into about half.

Scored per citation. Redline "flags" a citation when its verdict is FABRICATED. A flag is a true
positive when the citation carries any injected error, and a false positive otherwise. Spans the
authors label `optional` (typos in the original briefs) are not scored, as in the paper.

    python bench/phantom.py              # eval split (390 excerpts)    -> bench/results/phantom-eval.json
    python bench/phantom.py aux_train    # held-out split, never used to tune Redline
"""
import collections
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from redline.store import Store  # noqa: E402
from redline.verify import check  # noqa: E402
from redline.reporters import phantom_series  # noqa: E402

SPLIT = sys.argv[1] if len(sys.argv) > 1 else "eval"  # "aux_train" is held out: never used to tune Redline
DATA = ROOT / "data" / "raw" / "phantom" / f"{SPLIT}.jsonl"
URL = f"https://huggingface.co/datasets/ai-law-society-lab/Legal_Phantom_Citation/resolve/main/{SPLIT}.jsonl"
OUT = ROOT / "bench" / "results" / f"phantom-{SPLIT}.json"
# Errors in the original briefs that the dataset does not label, each confirmed with evidence.
SOURCE_ERRORS = {(e["excerpt"], e["citation"]): e["evidence"]
                 for e in json.loads((ROOT / "bench" / "source_errors.json").read_text())["errors"]}
TYPES = ["non_existent_citation", "case_name_mismatch", "wrong_pincite", "misquote", "content_misrepresentation"]
CITE = re.compile(r"(\d{1,4})\s+([A-Za-z][A-Za-z0-9.' ]*?)\s+(?:at\s+)?(\d{1,6})(?![\w])")
HELD = {"us", "f3d"}


def _key(vol, rep, page):
    return (int(vol), re.sub(r"[\s.]", "", rep).lower(), int(page))


def keys_in(text):
    return {_key(*m.groups()) for m in CITE.finditer(text)}


def load():
    if not DATA.exists():
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_bytes(urllib.request.urlopen(URL, timeout=120).read())
    return [json.loads(line) for line in DATA.open()]


def main():
    rows = load()
    store = Store()
    by_type = {t: collections.Counter() for t in TYPES}
    flags = collections.Counter()
    verdicts = collections.Counter()
    false_alarms, clean_flagged, clean_total, misses_in_scope, source_errors = [], 0, 0, [], []
    started = time.perf_counter()
    for row in rows:
        gold = {}  # citation key -> set of types
        never_published = set()  # keys whose reporter series was never published
        for cite, types in (row.get("list_hallucination_types") or {}).items():
            for k in keys_in(cite):
                gold.setdefault(k, set()).update(t for t in types if t in TYPES)
            for p in phantom_series(cite, []):
                never_published.add(_key(p["volume"], p["reporter"], p["page"]))
        optional = set()
        for span, label in (row.get("list_hallucinations") or {}).items():
            if label == "optional":
                optional |= keys_in(span)
            elif label in TYPES:
                # 24 entries carry labels only here, not in list_hallucination_types
                for k in keys_in(span) if label in ("non_existent_citation", "case_name_mismatch") else ():
                    gold.setdefault(k, set()).add(label)
                for p in phantom_series(span, []):
                    never_published.add(_key(p["volume"], p["reporter"], p["page"]))
        result = check(store, row["text"])
        flagged = set()
        for c in result["citations"]:
            k = _key(c["volume"], c["reporter"], c["page"]) if c["volume"] and c["page"] else None
            verdicts[c["verdict"]] += 1
            if c["verdict"] != "FABRICATED" or k is None:
                continue
            flagged.add(k)
            same_volume = {g for g in gold if g[:2] == k[:2]}  # "687 F.3d 671" and "687 F.3d at 675": one case
            if k in optional:
                flags["optional"] += 1
            elif k in gold or same_volume:
                flags["true_positive"] += 1
                flagged |= same_volume
            elif (row["filename"], c["text"]) in SOURCE_ERRORS:
                flags["source_error"] += 1
                source_errors.append({"excerpt": row["filename"], "citation": c["text"],
                                      "evidence": SOURCE_ERRORS[(row["filename"], c["text"])]})
            else:
                flags["false_positive"] += 1
                false_alarms.append({"excerpt": row["filename"], "citation": c["text"], "reason": c["reason"]})
        if not gold:
            clean_total += 1
            clean_flagged += bool(flagged - optional)
        for k, types in gold.items():
            # within reach: a reporter Redline holds, or a series that was never published
            in_scope = k[1] in HELD or k in never_published
            for t in types:
                by_type[t]["total"] += 1
                by_type[t]["caught"] += k in flagged
                if in_scope:
                    by_type[t]["in_scope"] += 1
                    by_type[t]["caught_in_scope"] += k in flagged
                    if k not in flagged and t in ("non_existent_citation", "case_name_mismatch"):
                        misses_in_scope.append({"excerpt": row["filename"], "citation": f"{k[0]} {k[1]} {k[2]}", "type": t})
    seconds = time.perf_counter() - started
    flagged_total = flags["true_positive"] + flags["false_positive"] + flags["source_error"]
    adjudicated = flags["true_positive"] + flags["source_error"]
    out = {
        "dataset": f"LePhantomCite {SPLIT} split (Liu, Stammbach & Henderson 2026), CC BY 4.0",
        "excerpts": len(rows), "seconds": round(seconds, 2), "ms_per_excerpt": round(1000 * seconds / len(rows), 1),
        "citations_checked": sum(verdicts.values()), "verdicts": dict(verdicts),
        "flags": dict(flags),
        "precision": round(flags["true_positive"] / flagged_total, 4) if flagged_total else None,
        "precision_with_source_errors": round(adjudicated / flagged_total, 4) if flagged_total else None,
        "source_errors": source_errors,
        "clean_excerpts": clean_total, "clean_excerpts_with_a_flag": clean_flagged,
        "recall_by_type": {t: {"caught": c["caught"], "total": c["total"],
                               "caught_in_scope": c["caught_in_scope"], "in_scope": c["in_scope"]}
                           for t, c in by_type.items()},
        "false_alarms": false_alarms, "misses_in_scope": misses_in_scope,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"{len(rows)} excerpts, {out['citations_checked']} citations, {seconds:.1f}s ({out['ms_per_excerpt']} ms each)")
    print(f"flags: {dict(flags)}  precision: {out['precision']} "
          f"(counting confirmed source-brief errors as correct: {out['precision_with_source_errors']})")
    print(f"clean excerpts flagged: {clean_flagged} of {clean_total}")
    for t, c in by_type.items():
        print(f"  {t:<26} caught {c['caught']:>3}/{c['total']:<3}  in scope {c['caught_in_scope']:>3}/{c['in_scope']}")
    return out


if __name__ == "__main__":
    main()
