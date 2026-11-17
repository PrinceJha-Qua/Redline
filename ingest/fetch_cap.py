"""Download Caselaw Access Project metadata for whole reporters.

CAP (Harvard Law School Library) publishes one CasesMetadata.json per reporter volume at
static.case.law/<reporter>/<volume>/. Each record carries the case name, court, date, first and
last page, parallel citations, and the citations the opinion makes, already resolved to case ids.

    python -m ingest.fetch_cap us f3d        # resumable; skips volumes already on disk
"""
import http.client
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://static.case.law"
RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "cap"
UA = {"User-Agent": "redline-ingest/0.1"}


def _get(url, tries=4):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == tries - 1:
                raise
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
    return None


def fetch_reporter(slug, workers=8):
    out = RAW / slug
    out.mkdir(parents=True, exist_ok=True)
    vols_file = out / "_volumes.json"
    if not vols_file.exists():
        vols_file.write_bytes(_get(f"{BASE}/{slug}/VolumesMetadata.json"))
    folders = sorted({v["volume_folder"] for v in json.loads(vols_file.read_text())}, key=lambda f: (len(f), f))
    todo = [f for f in folders if not (out / f"{f}.json").exists()]
    print(f"{slug}: {len(folders)} volumes, {len(todo)} to download", flush=True)

    def one(folder):
        body = _get(f"{BASE}/{slug}/{folder}/CasesMetadata.json")
        if body is None:
            return folder, False
        json.loads(body)  # refuse to keep a truncated download
        tmp = out / f"{folder}.json.part"
        tmp.write_bytes(body)
        tmp.rename(out / f"{folder}.json")
        return folder, True

    missing = []
    with ThreadPoolExecutor(workers) as pool:
        for n, (folder, ok) in enumerate(pool.map(one, todo), 1):
            if not ok:
                missing.append(folder)
            if n % 100 == 0:
                print(f"  {slug}: {n}/{len(todo)}", flush=True)
    if missing:
        print(f"  {slug}: no metadata published for volumes {', '.join(missing)}")
    print(f"{slug}: done")


if __name__ == "__main__":
    for reporter in sys.argv[1:] or ["us", "f3d"]:
        fetch_reporter(reporter)
