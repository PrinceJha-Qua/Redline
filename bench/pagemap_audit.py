"""Find pages that courts cite as the start of a case, where Redline's page map has no case starting.

Each opinion in the Caselaw Access Project lists the citations it makes, including ones CAP could not
link to a case. If two or more different courts cite "657 F.3d 1323" and no case in the data starts
on page 1323, a real case exists there that the data is missing or misplaces. Redline must never call
such a citation fabricated.

    python bench/pagemap_audit.py      # -> data/pagemap_audit.json, read by the store builder
"""
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "cap"
OUT = ROOT / "data" / "pagemap_audit.json"
REPORTERS = {"us": ("U.S.", "US"), "f3d": ("F.3d", "F3d")}
CITE = re.compile(r"^(\d+)\s+(.+?)\s+(\d+)\s*$")
MIN_COURTS = 2


def norm(rep):
    return re.sub(r"[\s.]", "", rep).lower()


def main():
    starts = collections.defaultdict(set)      # volume key -> first pages in the data
    ranges = collections.defaultdict(list)     # volume key -> (first, last, name)
    by_norm = {norm(a): p for a, p in REPORTERS.values()}
    for slug, (abbr, prefix) in REPORTERS.items():
        for f in (RAW / slug).glob("[0-9]*.json"):
            for r in json.loads(f.read_text()):
                pages = re.findall(r"\d+", f"{r.get('first_page')} {r.get('last_page')}")
                if pages:
                    key = f"{prefix}:{f.stem}"
                    starts[key].add(int(pages[0]))
                    ranges[key].append((int(pages[0]), int(pages[-1]), r.get("name_abbreviation", "")))
    cited = collections.defaultdict(set)       # (volume key, page) -> citing case ids
    for slug in ("us", "f3d"):
        for f in (RAW / slug).glob("[0-9]*.json"):
            for r in json.loads(f.read_text()):
                for t in r.get("cites_to") or []:
                    m = CITE.match(t.get("cite") or "")
                    if not m or norm(m.group(2)) not in by_norm:
                        continue
                    cited[(f"{by_norm[norm(m.group(2))]}:{m.group(1)}", int(m.group(3)))].add(r["id"])
    orphans = collections.defaultdict(list)
    for (key, page), who in cited.items():
        if len(who) >= MIN_COURTS and key in starts and page not in starts[key]:
            inside = next((n for a, b, n in ranges[key] if a <= page <= b), None)
            orphans[key].append({"page": page, "courts": len(who), "inside": inside})
    total = sum(len(v) for v in orphans.values())
    inside = sum(1 for v in orphans.values() for o in v if o["inside"])
    report = {k: sorted(v, key=lambda o: o["page"]) for k, v in sorted(orphans.items())}
    OUT.write_text(json.dumps({
        "rule": f"a page cited as a case's first page by {MIN_COURTS}+ different courts, where the data has no case starting",
        "cited_pages_checked": sum(1 for (k, p), w in cited.items() if len(w) >= MIN_COURTS and k in starts),
        "orphan_pages": total, "orphans_inside_another_case": inside, "volumes": report}, indent=1))
    checked = sum(1 for (k, p), w in cited.items() if len(w) >= MIN_COURTS and k in starts)
    print(f"{checked:,} pages cited by {MIN_COURTS}+ courts; {total:,} have no case starting there "
          f"({inside:,} of them fall inside another case), in {len(orphans):,} volumes")
    worst = sorted(orphans.items(), key=lambda kv: -len(kv[1]))[:8]
    print("most affected volumes:", [(k, len(v)) for k, v in worst])
    for key in ("F3d:657", "F3d:21", "F3d:925", "F3d:174"):
        print(key, report.get(key, [])[:6])


if __name__ == "__main__":
    main()
