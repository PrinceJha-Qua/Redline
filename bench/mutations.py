"""Break each safeguard on purpose and check that the test suite notices.

A test suite that still passes with a guard removed does not protect that guard. Each mutation below
edits one line of a copy of the package, runs the tests against the copy, and expects a failure.

    python bench/mutations.py        # -> bench/results/mutations.json
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bench" / "results" / "mutations.json"

MUTATIONS = [
    ("a volume whose page map disagrees with the courts is still used as proof", "redline/verify.py",
     'if not volume["complete"]:', "if False:"),
    ("a page courts cite as a case start, missing from the data, is called fabricated", "redline/verify.py",
     'if page in set(volume["cited_starts"] or []):', "if False:"),
    ("a page of short orders is called fabricated", "redline/verify.py",
     'if starts and page in set(volume["order_pages"] or []):', "if False:"),
    ("a shared last page between two opinions is called fabricated", "redline/verify.py",
     "if at_page and not strictly_inside:", "if False:"),
    ("names never agree", "redline/verify.py",
     "return any(_agree(r, actual, common) for r in _readings(cite)) if _readings(cite) else True", "return False"),
    ("a passing mention counts as reliance", "redline/status.py",
     "if parenthetical and not _NOISE.search(parenthetical):", "if True:"),
    ("a case cited after it was overruled counts as resting on it", "redline/status.py",
     "WHERE m.status IS NOT NULL AND by.year >= c.year AND by.id <> c.id",
     "WHERE m.status IS NOT NULL AND by.id <> c.id"),
    ("checking as of a date ignores the date", "redline/status.py",
     "return as_of is None or (year or 0) <= as_of", "return True"),
    ("a repair ignores which side of the 'v.' a party is on", "redline/agent.py",
     'same = [h for h in rows if h["cite"] != exclude and _same_parties(parties, h["name"])]',
     'same = [h for h in rows if h["cite"] != exclude]'),
    ("a repair accepts any shorter word as an abbreviation", "redline/agent.py",
     "return w == h or (aw and len(w) < len(h) and _abbreviates(w, h)) or (ah and len(h) < len(w) and _abbreviates(h, w))",
     "return w == h or _abbreviates(w, h) or _abbreviates(h, w)"),
    ("a what-if is not rolled back", "redline/store.py",
     "self._con.rollback()\n                self._con.autocommit = True",
     "self._con.autocommit = True"),
    ("find_authority ranks overruled cases first", "redline/agent.py",
     'ranked.sort(key=lambda e: (e["status"] in ("overruled", "overruled in part"), -e["score"]))',
     'ranked.sort(key=lambda e: -e["score"])'),
]


def run(desc, path, old, new):
    with tempfile.TemporaryDirectory(prefix="redline-mut-") as tmp:
        tmp = Path(tmp)
        for d in ("redline", "tests", "web", "ingest", "bench"):
            shutil.copytree(ROOT / d, tmp / d, ignore=shutil.ignore_patterns("__pycache__", "results"))
        (tmp / "data").symlink_to(ROOT / "data")
        target = tmp / path
        src = target.read_text()
        assert src.count(old) == 1, f"mutation anchor not found exactly once in {path}: {old!r}"
        target.write_text(src.replace(old, new))
        t = time.time()
        p = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "tests"],
                           cwd=tmp, capture_output=True, text=True, env={"PYTHONPATH": str(tmp), "PATH": "/usr/bin:/bin"})
        failed = [line.split(" ")[1] for line in p.stdout.splitlines() if line.startswith("FAILED")]
        return {"mutation": desc, "file": path, "killed": p.returncode != 0, "caught_by": failed[:3],
                "seconds": round(time.time() - t, 1)}


def main():
    results = []
    for m in MUTATIONS:
        r = run(*m)
        results.append(r)
        print(f"{'killed  ' if r['killed'] else 'SURVIVED'} {r['mutation']}  {r['caught_by'][:1]}", flush=True)
    killed = sum(r["killed"] for r in results)
    OUT.write_text(json.dumps({"mutations": len(results), "killed": killed, "results": results}, indent=2))
    print(f"{killed} of {len(results)} mutations caught by the tests -> {OUT.relative_to(ROOT)}")
    return 0 if killed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
