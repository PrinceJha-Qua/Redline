"""Find case citations in a brief and read what each one claims: volume, reporter, page,
pin cite, year, court and case name.

eyecite (Free Law Project) finds the citations. Names, years and courts are read from the text
around each citation, because in a string of citations eyecite can attach one citation's year to
another.
"""
import logging
import re
import unicodedata
from difflib import SequenceMatcher

from eyecite import get_citations
from eyecite.models import FullCaseCitation, ShortCaseCitation

from .reporters import phantom_series

logging.getLogger("eyecite").setLevel(logging.ERROR)  # "Unknown overlap case" notices on string cites

# Reporters Redline holds in full: what eyecite calls them -> how the store keys them.
COVERED = {"U.S.": "US", "F.3d": "F3d"}
# Parallel reporters for Supreme Court cases, looked up through (:Citation) nodes.
PARALLEL = {"S. Ct.": "S.Ct.", "L. Ed.": "L.Ed.", "L. Ed. 2d": "L.Ed. 2d"}

_YEAR = re.compile(r"^[\s,]*(?:at\s+)?[\d\s,\-–—n.]*\(([^()]*?)\b(1[6-9]\d\d|20\d\d)\)")
_STOP = {"v", "vs", "the", "of", "and", "in", "re", "ex", "rel", "inc", "co", "corp", "ltd", "llc", "et",
         "al", "a", "an", "for", "on", "to", "at", "by", "us", "u", "s", "united", "states", "america",
         "company", "corporation", "see", "also", "cf", "eg", "e", "g", "but", "compare", "with", "accord",
         "citing", "quoting", "id", "supra", "ibid", "dist", "llp", "plc", "na", "n", "ass", "assn",
         # English words that open sentences and clauses, never a party's name
         "if", "when", "while", "because", "although", "though", "since", "unless", "until", "after",
         "before", "where", "whether", "then", "thus", "here", "there", "this", "that", "these", "those",
         "under", "following", "test", "contra", "or", "nor", "so", "yet", "however", "moreover", "finally",
         "first", "second", "third", "like", "unlike", "as", "from", "into", "with", "without", "per"}


_JOINERS = {"of", "the", "&", "ex", "rel.", "rel", "de", "la", "for", "in", "re"}
_SIGNALS = {"see", "also", "cf", "accord", "compare", "but", "in", "under", "following", "citing", "quoting", "and"}


_ABBREVIATIONS = {"inc", "co", "corp", "ltd", "llc", "bd", "educ", "elec", "dep't", "dept", "ass'n", "assn", "nat'l",
                  "natl", "dist", "univ", "comm'n", "commn", "comm'r", "gen", "admin", "sec'y", "int'l", "intern",
                  "mfg", "mut", "ins", "fed", "gov't", "govt", "auth", "transp", "envtl", "env't", "hosp", "med",
                  "ctr", "cnty", "twp", "sch", "indus", "pub", "serv", "servs", "sys", "tel", "bros", "assocs",
                  "cal", "fla", "tex", "ill", "mich", "mass", "penn", "pa", "wash", "jr", "sr", "st", "mt", "ft",
                  "no", "ex", "rel", "al", "am", "s", "n", "e", "w", "r", "ry", "r.r", "l.p", "p.c", "p.a", "atty",
                  "att'y", "gen.", "emps", "emp", "prot", "res", "def", "agric", "comm", "coal", "found", "dev",
                  "mgmt", "prods", "props", "sav", "fin", "invs", "techs", "tech", "cmty", "ref", "reg'l",
                  "condo", "assoc", "assocs", "intern", "int'l", "pharm", "pharms", "indus", "mktg", "litig", "soc",
                  "servs", "chem", "elecs", "enters", "grp", "hldgs", "holdings", "info", "ins", "lab", "labs",
                  "mem", "mgt", "nw", "ne", "sw", "se", "prop", "prot", "reins", "rest", "ret", "sch", "sols",
                  "telecomms", "transp", "u", "util", "utils", "v", "dep’t", "ass’n", "nat’l", "int’l", "gov’t",
                  "comm’n", "sec’y", "att’y", "reg’l", "envtl", "fid", "guar", "inv", "invs", "liab", "mfrs", "pac",
                  "petro", "pub", "res", "sys", "tr", "twp", "univ", "vill", "brd", "comms", "cos", "dists"}


_SENTENCE_ENDERS = {"act", "acts", "code", "amendment", "amendments", "constitution", "clause", "rule", "rules",
                    "court", "courts", "circuit", "congress", "statute", "statutes", "regulation", "regulations",
                    "section", "title", "chapter", "article", "order", "opinion", "decision", "claim", "claims",
                    "evidence", "law", "laws", "treaty", "convention", "agency", "government", "states", "state",
                    "commission", "board", "secretary", "district", "jury", "trial", "here", "there", "it"}


def _abbreviation(word):
    """A word ending in a period that is a legal abbreviation ("Balt.", "Mach.", "Elec.") rather than the end
    of a sentence. Capitalized words are taken as abbreviations unless they usually end sentences ("Act.");
    missing a sentence end only makes name matching more lenient, never stricter."""
    core = word.rstrip(".").strip("(\"'*")
    if core.lower() in _ABBREVIATIONS or len(core) <= 2 or "." in core:
        return True
    return core[:1].isupper() and core.lower() not in _SENTENCE_ENDERS


def _fold(text):
    """Drop accents and undo the commonest OCR swaps: "Muñiz" -> "muniz", "Cornejo" ~ "Camejo"."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return text.lower().replace("rn", "m").replace("ri", "n")  # "Cornejo"/"Camejo", "Marin"/"Mann"


def name_tokens(text):
    text = re.sub(r"\b([A-Za-z])\.(?=[A-Za-z]\b)", r"\1", text)  # "J.J." -> "JJ."
    words = re.findall(r"[a-z0-9]+", _fold(text).replace("'", "").replace("’", ""))
    return [w for w in words if w not in _STOP and not w.isdigit() and len(w) > 1]


def _abbreviates(short, long):
    """'natl' / 'national', 'commr' / 'commissioner', 'assn' / 'association': same first letter, and the
    short form's letters appear in order in the long word."""
    if len(short) < 3 or short[0] != long[0] or len(short) < 0.3 * len(long):
        return False
    it = iter(long)
    return all(ch in it for ch in short)


def _same_word(c, a):
    if c == a:
        return True
    short, long = sorted((c, a), key=len)
    if _abbreviates(short, long):
        return True
    if len(c) >= 5 and len(c) == len(a) and c[1:] == a[1:]:
        return True  # an OCR'd first letter: Kasalo / Rasalo
    # spelling and OCR variants keep the first letter: Mazzarella/Marzzarella, Guernsey/Gurnsey
    return len(c) >= 4 and len(a) >= 4 and c[0] == a[0] and SequenceMatcher(None, c, a).ratio() >= 0.8


def comparable(name):
    return bool(name_tokens(name))


def names_agree(cited, actual, common=frozenset()):
    """True unless the cited name and the real name share nothing that identifies a case.

    Lenient on purpose: abbreviations ("Nat'l"), acronyms ("NRDC"), short forms ("Chevron"), spelling and
    OCR variants all count as agreement. A word found in many case names (`common`: "Fire", "Bank",
    "Smith") is weak evidence on its own: two of them must match, so "Parker v. Blauvelt Volunteer
    Fire Co." does not match "Mount Vernon Fire Insurance".
    """
    cited_t, actual_t = name_tokens(cited), name_tokens(actual)
    if not cited_t or not actual_t:
        return True  # nothing to compare
    plain = re.sub(r"['’]", "", _fold(actual))  # "Ass'n" -> "assn"
    initials = "".join(w[0] for w in re.findall(r"[a-z]+", plain)
                       if w not in {"of", "the", "and", "v", "for", "in", "on", "ex", "rel", "a", "an"})
    matched = [c for c in cited_t if any(_same_word(c, a) for a in actual_t)
               or (len(c) >= 3 and c.isalpha() and c in initials)]
    if any(c not in common for c in matched):
        return True  # a distinctive word in common: "Varghese", "Chevron", "NRDC"
    # Only common words match. Enough of them still identify the case ("City of Chicago v. Morales");
    # one alone does not ("Parker v. Blauvelt Volunteer Fire Co." vs "Mount Vernon Fire Insurance").
    return len(set(matched)) >= min(2, len(set(cited_t)))


_CAPTION = re.compile(r"\b(?:In re|Ex parte|In the Matter of|Matter of|ex rel\.)", re.I)


def is_caption(name):
    """"In re Lupron Mktg. Litig." or "United States ex rel. Newell": the data names such cases by their
    parties, so a mismatch in name proves nothing."""
    return bool(_CAPTION.search(name or ""))


def _cited_name(text, cite, start):
    """The words before the citation, back to the previous citation boundary."""
    window = text[max(0, start - 160):start].replace("*", "").replace("_", " ")
    window = re.sub(r"\s\([A-Z][A-Za-z.]{1,20}\)(?=\s+v\.)", "", window)  # "Standard Oil Co. (Indiana) v. ..."
    cut = max(window.rfind(";"), window.rfind(")"), window.rfind("("), window.rfind("\n"))
    window = window[cut + 1:] if cut >= 0 else window
    if not re.search(r",[\s*_]*$", window):
        return ""  # "...established in BMW v. Gore. 312 F.3d 998": the name belongs to another sentence
    window = re.sub(r"\s+", " ", window).strip(" ,.")
    joined = list(re.finditer(r"\d[\d\-–]*\)?,?\s+(?:and|or)\s+", window))
    if joined:  # "Brown, 334 F.3d 1161, and United States v. Turner": the name starts after "and"
        window = window[joined[-1].end():]
    at = max(window.rfind(" v. "), window.rfind(" v "))
    if at < 0:
        m = re.search(r"\b(?:In re|Ex parte|Matter of|In the Matter of)\s.*$", window)
        return m.group(0)[-140:] if m else ""  # prose, not a case name
    # Walk back from "v." over the plaintiff's name: capitalised words and the small words inside names.
    left, kept = window[:at].split(" "), []
    for word in reversed(left):
        bare = word.strip(",.;:()\"'")
        if word.rstrip(",").endswith(".") and not _abbreviation(word.rstrip(",")) and kept:
            break  # "...the Clean Water Act. Southwestern Elec. Power Co. v. EPA": the sentence ended
        if bare and (bare[0].isupper() or bare[0].isdigit() or bare.lower() in _JOINERS) and len(kept) < 8:
            kept.append(word)
        else:
            break
    while kept and kept[-1].strip(",.").lower() in _JOINERS | _SIGNALS:
        kept.pop()  # a name does not start with "of" or "See"
    return (" ".join(reversed(kept)) + window[at:])[-140:].strip(" ,.")


_SHORT_NAME = re.compile(r"([A-Z][\w.'’&\- ]{1,60}?)[\s*_]*,\s*$")
_LEADING_SIGNALS = re.compile(r"^(?:(?:see|also|cf|accord|e\.g|but|compare|contra)[.,]?\s+)+", re.I)


def _short_name(text, start):
    """The short case name right before a citation: "Fowler, 344 F.3d at 1211" -> "Fowler"."""
    window = re.sub(r"\s+", " ", text[max(0, start - 80):start])
    window = window.replace("*", "").replace("_", "")
    m = _SHORT_NAME.search(window)
    if not m:
        return ""
    name = m.group(1).strip()
    # "Village of Barrington, Illinois, 636 F.3d at 659": take the segment before the last comma too
    before = window[:m.start()].rstrip()
    if before.endswith(","):
        prev = re.search(r"([A-Z][\w.'’&\- ]{1,60}?)\s*,$", before)
        if prev and not _LEADING_SIGNALS.fullmatch(prev.group(1) + " ") and not prev.group(1).endswith("."):
            name = f"{prev.group(1).strip()}, {name}"
    name = _LEADING_SIGNALS.sub("", name).strip(" ,")
    words = name.split(" ")  # keep only the last sentence: "States may not execute them. Atkins" -> "Atkins"
    for i in range(len(words) - 1, 0, -1):
        # a sentence ends on a lowercase word ("them."); "ARW Expl. Corp." is one name
        if words[i - 1].endswith(".") and words[i - 1][:1].islower() and words[i][:1].isupper():
            name = " ".join(words[i:])
            break
    if " v. " in name or len(re.sub(r"[^A-Za-z]", "", name)) < 4 or not name[:1].isupper():
        return ""
    if any(w.isalpha() and w.islower() and w not in _JOINERS for w in name.replace(",", " ").split()):
        return ""  # prose, not a name: "the Federal Circuit affirmed, 148 F.3d 1343"
    if name.split()[0].lower() in {"id", "ibid", "supra", "the", "this", "that", "in", "as", "under", "and", "we",
                                   "our", "it", "they", "he", "she", "its", "their", "his", "her", "court"}:
        return ""
    return name


def extract(text):
    """Every case citation in `text`, in order: full citations and short forms that name a volume
    ("Fowler, 344 F.3d at 1211"). "Id." and "supra" are skipped: they carry no volume or page."""
    found = []
    if not text or not text.strip():
        return found  # eyecite raises on empty input
    flat = re.sub(r"\s", " ", text)  # same length, so spans still point into the original text
    for c in get_citations(flat):
        short = isinstance(c, ShortCaseCitation)
        if not isinstance(c, FullCaseCitation) and not short:
            continue
        start, end = c.span()
        reporter = c.corrected_reporter() or c.groups.get("reporter", "")
        after = flat[end:end + 80]
        m = _YEAR.match(after)
        if m and (re.search(r"\d{3,}", m.group(1)) or re.search(r"U\.\s?S\.|S\.\s?Ct|L\.\s?Ed|\bat\b|\bNos?\.", m.group(1))
                  or m.group(1).rstrip().endswith("-")):
            m = None  # "(citing Graham, 490 U.S. at 395, 109 S.Ct. 1865)": 1865 is a page, not a year
        year = int(m.group(2)) if m else None
        court = m.group(1).strip(" ,") if m else ""
        pin = c.metadata.pin_cite or ""
        pin_page = int(re.match(r"\D*(\d+)", pin).group(1)) if re.match(r"\D*(\d+)", pin) else None
        page = c.groups.get("page") or ""
        found.append({
            "text": c.matched_text(),
            "span": [start, end],
            "volume": int(c.groups["volume"]) if str(c.groups.get("volume", "")).isdigit() else None,
            "reporter": reporter,
            "page": int(page) if page.isdigit() else None,
            "page_text": page,
            "pin": pin_page,
            "year": year,
            "court": court,
            "name": "" if short else _cited_name(flat, c, start),
            "short_name": _short_name(flat, start),
            "short": short,
            # eyecite's reading of the parties; used only to be more lenient when matching names
            "parties": "" if short else " ".join(x for x in (c.metadata.plaintiff, c.metadata.defendant) if x),
        })
    taken = [tuple(f["span"]) for f in found]
    for p in phantom_series(flat, taken):
        m = _YEAR.match(flat[p["span"][1]:p["span"][1] + 80])
        p.update({"page_text": str(p["page"]), "pin": None, "year": int(m.group(2)) if m else None,
                  "court": m.group(1).strip(" ,") if m else "", "name": _cited_name(flat, None, p["span"][0]), "parties": "",
                  "short_name": "", "short": False})
        found.append(p)
    found.sort(key=lambda c: c["span"][0])
    return found
