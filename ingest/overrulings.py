"""Turn Wikipedia's list of overruled US Supreme Court decisions into data/overrulings.json.

Source: https://en.wikipedia.org/wiki/List_of_overruled_United_States_Supreme_Court_decisions
(CC BY-SA 4.0). Each table row pairs an overruled decision with the decision that overruled it.

    python -m ingest.overrulings            # downloads the page once, then parses it
"""
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "data" / "raw" / "wikipedia" / "overruled.wiki"
OUT = ROOT / "data" / "overrulings.json"
PAGE = "List_of_overruled_United_States_Supreme_Court_decisions"
URL = f"https://en.wikipedia.org/w/index.php?title={PAGE}&action=raw"

# "410 U.S. 113 (1973)", "80 U.S. (13 Wall.) 29 (1872)", "347 US 483 (1954)", "609 U.S. ___ (2026)"
CITATION = re.compile(r"(\d+)\s+U\.?\s?S\.?\s+(?:\([^)]*\)\s+)?(\d+|_+)\s*\((\d{4})\)")
LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")


def _plain(text):
    text = re.sub(r"<ref[^>]*/>|<ref.*?</ref>", "", text, flags=re.S)
    text = LINK.sub(r"\1", text)
    return re.sub(r"\s+", " ", text.replace("''", "")).strip()


def _decisions(cell):
    """A cell can name more than one decision; return each with its U.S. citation."""
    plain = _plain(cell)
    found, start = [], 0
    for m in CITATION.finditer(plain):
        name = plain[start:m.start()].strip(" ,;")
        name = re.sub(r"^(and|\(in part\))\s+", "", name).strip(" ,;")
        tail = plain[m.end():m.end() + 40].lower()
        found.append({
            "name": name, "vol": int(m.group(1)),
            "page": None if m.group(2).startswith("_") else int(m.group(2)),
            "year": int(m.group(3)), "partial": "in part" in tail,
        })
        start = m.end()
    return found


def parse(wikitext):
    rows, section, topic, cells = [], "", "", []

    def flush():
        if len(cells) >= 2:
            for old in _decisions(cells[0]):
                for new in _decisions(cells[1]):
                    rows.append({"overruled": old, "overruling": new, "partial": old["partial"],
                                 "topic": " / ".join(t for t in (section, topic) if t)})
        cells.clear()

    for line in wikitext.splitlines():
        if line.startswith("=="):
            flush()
            section, topic = line.strip("= ").strip(), ""
        elif line.startswith(";"):
            flush()
            topic = _plain(line[1:])
        elif line.startswith("|-") or line.startswith("|}") or line.startswith("{|"):
            flush()
        elif line.startswith("|"):
            cells.append(line[1:])
        elif cells and not line.startswith("!"):
            cells[-1] += " " + line  # a cell continued on the next line
    flush()
    return rows


def build():
    if not WIKI.exists():
        WIKI.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": "redline-ingest/0.1"})
        WIKI.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    rows = parse(WIKI.read_text(encoding="utf-8"))
    OUT.write_text(json.dumps({
        "source": f"Wikipedia, {PAGE.replace('_', ' ')} (CC BY-SA 4.0)",
        "url": f"https://en.wikipedia.org/wiki/{PAGE}", "rows": rows}, indent=1, ensure_ascii=False))
    print(f"{len(rows)} overrulings -> {OUT.relative_to(ROOT)}")
    return rows


if __name__ == "__main__":
    build()
