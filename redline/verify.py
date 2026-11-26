"""Give every citation in a brief one of three verdicts, with the evidence behind it.

VERIFIED      the case exists; its status (good law, caution, overruled) comes from status.py
FABRICATED    the citation points into a reporter volume Redline holds in full, and cannot be right:
              the page belongs to another case, lies past the volume's last page, or starts a case
              with a different name
UNVERIFIABLE  outside Redline's coverage; never called fake

Every verdict comes from a graph query. No language model writes or changes one.
"""
import re
from functools import lru_cache

from .citations import COVERED, PARALLEL, comparable, extract, is_caption, names_agree as _agree, name_tokens
from .reporters import year_outside_series
from .status import STANDS_ON, status_of

_CASE_COLUMNS = ("c.id AS id, c.name AS name, c.title AS title, c.cite AS cite, c.court AS court, c.year AS year, "
                 "c.first_page AS first_page, c.last_page AS last_page, c.stub AS stub")


def _names(case):
    """Short name plus full caption, so co-defendants and relators match."""
    return f"{case['name']} {case.get('title') or ''}"

_AT_PAGE = f"""
MATCH (:Volume {{key: $key}})-[:CONTAINS]->(c:Case)
WHERE c.first_page <= $page AND c.last_page >= $page
RETURN {_CASE_COLUMNS} ORDER BY c.first_page DESC
"""
_BY_ID = f"MATCH (c:Case {{id: $id}}) RETURN {_CASE_COLUMNS}"
_VOLUME = ("MATCH (v:Volume {key: $key}) RETURN v.last_page AS last_page, v.cases AS cases, "
           "v.order_pages AS order_pages, v.cited_starts AS cited_starts, v.complete AS complete")
_PARALLEL = f"MATCH (:Citation {{text: $text}})-[:CITATION_OF]->(c:Case) RETURN {_CASE_COLUMNS}"
_NAMED_IN_VOLUME_PAGES = """
MATCH (:Volume {key: $key})-[:CONTAINS]->(c:Case)
WHERE toLower(c.name) CONTAINS $word
RETURN c.name AS name, c.title AS title, c.cite AS cite, c.first_page AS first_page, c.last_page AS last_page LIMIT 10
"""
_NAMED_IN_VOLUME = """
MATCH (:Volume {key: $key})-[:CONTAINS]->(c:Case)
WHERE toLower(c.name) CONTAINS $word
RETURN c.name AS name, c.cite AS cite LIMIT 3
"""


COMMON_SHARE = 0.001  # a word in 0.1% or more of all case names is too common to identify a case


@lru_cache(maxsize=4)
def common_words(store):
    names = store.query("MATCH (c:Case) RETURN c.name AS n")
    counts = {}
    for r in names:
        for w in set(name_tokens(r["n"])):
            counts[w] = counts.get(w, 0) + 1
    floor = COMMON_SHARE * len(names)
    return frozenset(w for w, n in counts.items() if n >= floor)


@lru_cache(maxsize=4)
def coverage(store):
    rows = store.query("MATCH (r:Reporter) RETURN r.abbr AS abbr, r.name AS name, r.first_vol AS first_vol, "
                       "r.last_vol AS last_vol, r.first_year AS first_year, r.last_year AS last_year, "
                       "r.complete AS complete ORDER BY r.abbr DESC")
    return {r["abbr"]: r for r in rows}


def _coverage_text(store):
    return ", ".join(f"{r['abbr']} vols. {r['first_vol']}–{r['last_vol']} ({r['first_year']}–{r['last_year']})"
                     for r in coverage(store).values())


def _short(case):
    return f"{case['name']}, {case['cite']} ({case['court']} {case['year']})".replace("(U.S. ", "(")


def _evidence_case(case, role):
    return {"id": case["id"], "label": case["name"], "cite": case["cite"], "year": case.get("year"), "role": role}


def _verified(store, cite, case, warnings, note="", as_of=None):
    st = status_of(store, case, as_of)
    if as_of and case.get("year") and case["year"] > as_of:
        warnings = warnings + [f"Decided in {case['year']}, after {as_of}: a brief dated {as_of} could not cite it."]
    nodes = [_evidence_case(case, "cited")]
    edges = []
    for o in st["overruled_by"]:
        nodes.append(_evidence_case({**o, "court": "U.S."}, "overruling"))
        edges.append({"source": o["id"], "target": case["id"], "type": "OVERRULES"})
    for ch in st["stands_on"]:
        nodes.append(_evidence_case(ch["case"], "overruled"))
        nodes.append(_evidence_case({**ch["overruled_by"], "court": "U.S."}, "overruling"))
        edges.append({"source": case["id"], "target": ch["case"]["id"], "type": "CITES",
                      "label": ch["parenthetical"] or f"cited {ch['weight']}×"})
        edges.append({"source": ch["overruled_by"]["id"], "target": ch["case"]["id"], "type": "OVERRULES"})
    uniq = list({n["id"]: n for n in nodes}.values())
    reason = _short(case) + ". " + (note + " " if note else "") + st["reason"]
    if case.get("stub"):
        reason = (f"{case['name']}, {case['cite']} ({case['year']}). Decided after Redline's Supreme Court data ends "
                  f"(2014): the case is known from the overruling record, its own citations are not checked. ") + st["reason"]
    return {**cite, "verdict": "VERIFIED", "status": st["status"], "reason": reason.strip(),
            "warnings": warnings, "case": {k: case[k] for k in ("id", "name", "cite", "court", "year")},
            "overruled_by": st["overruled_by"], "stands_on": st["stands_on"],
            "stands_on_total": st.get("stands_on_total", len(st["stands_on"])),
            "mentions": st.get("mentions", []), "later": st.get("later", []),
            "evidence": {"nodes": uniq, "edges": edges, "query": _query(STANDS_ON, id=case["id"])}}


def _fabricated(cite, problem, reason, nodes=(), edges=(), query=None):
    return {**cite, "verdict": "FABRICATED", "problem": problem, "status": None, "reason": reason, "warnings": [],
            "case": None, "overruled_by": [], "stands_on": [], "stands_on_total": 0,
            "evidence": {"nodes": list(nodes), "edges": list(edges), "query": query}}


def _query(cypher, **params):
    """The Cypher behind a verdict, so anyone can rerun it against the store."""
    return {"cypher": " ".join(cypher.split()), "params": params}


def _unverifiable(cite, reason):
    return {**cite, "verdict": "UNVERIFIABLE", "status": None, "reason": reason, "warnings": [], "case": None,
            "overruled_by": [], "stands_on": [], "stands_on_total": 0,
            "evidence": {"nodes": [], "edges": [], "query": None}}


_CIRCUIT = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th|d)\s*Cir|\b(D\.\s?C|Fed)\.\s*Cir", re.I)


def _circuit(text):
    m = _CIRCUIT.search(text or "")
    if not m:
        return None
    return m.group(1) or m.group(2).replace(" ", "").upper().replace("FED", "Fed")


def _warnings(cite, case):
    out = []
    cited_court, real_court = _circuit(cite.get("court")), _circuit(case.get("court"))
    if cited_court and real_court and cited_court != real_court:
        out.append(f"Cited as {cite['court'].split(',')[0].strip().rstrip('.')}.; decided by the {case['court'].rstrip('.')}.".replace("..", "."))
    if cite["pin"] and not (case["first_page"] <= cite["pin"] <= case["last_page"]) and case["last_page"]:
        out.append(f"Pin cite {cite['pin']} is outside the case, which runs from page {case['first_page']} "
                   f"to {case['last_page']}.")
    if cite["year"] and case.get("year") and abs(cite["year"] - case["year"]) > 1:
        out.append(f"Cited as {cite['year']}; decided {case['year']}.")
    return out


def _cited(cite):
    return f"{cite['name'] or cite.get('short_name', '')} {cite.get('parties', '')}"


def _readings(cite):
    """The ways the brief names the case: the name Redline read, and eyecite's guess at the parties.
    Each is compared on its own, so noise in one cannot hide agreement in the other."""
    return [x for x in (cite["name"] or cite.get("short_name", ""), cite.get("parties", "")) if x and comparable(x)]


def verify(store, cite, as_of=None):
    reporter, vol, page = cite["reporter"], cite["volume"], cite["page"]
    cov = coverage(store)
    common = common_words(store)

    def names_agree(cited, actual):
        if cited is cite:  # compare every reading of the cited name
            return any(_agree(r, actual, common) for r in _readings(cite)) if _readings(cite) else True
        return _agree(cited, actual, common)

    if cite.get("phantom"):
        return _fabricated(cite, "no_such_series", cite["phantom"])
    held = cov.get(reporter)
    if held:  # publication years are only trusted for the reporters Redline holds (reporters-db dates vary)
        impossible = year_outside_series(reporter, cite["year"], held["first_year"])
        if impossible:
            return _fabricated(cite, "series_not_in_print", impossible)

    if reporter in PARALLEL and vol and page:
        rows = store.query(_PARALLEL, {"text": f"{vol} {PARALLEL[reporter]} {page}"})
        if rows:
            return _verified(store, cite, rows[0], _warnings(cite, rows[0]),
                             note=f"Parallel citation of {rows[0]['cite']}.", as_of=as_of)
        return _unverifiable(cite, f"{cite['text']} is a parallel Supreme Court citation that Redline cannot match "
                                   f"to a U.S. Reports page. Redline holds {_coverage_text(store)}.")

    if reporter not in COVERED or vol is None or page is None:
        return _unverifiable(cite, f"{reporter or 'This reporter'} is outside Redline's data, so this citation "
                                   f"cannot be checked. Redline holds {_coverage_text(store)}.")

    prefix, rep = COVERED[reporter], cov.get(reporter)
    if not rep or not (rep["first_vol"] <= vol <= rep["last_vol"]):
        stub = store.query(_BY_ID, {"id": f"{prefix}:{vol}:{page}"})
        if stub:
            return _verified(store, cite, stub[0], [], as_of=as_of)
        last = f"{rep['last_vol']} ({rep['last_year']})" if rep else "?"
        return _unverifiable(cite, f"Volume {vol} of {reporter} is after volume {last}, where Redline's "
                                   f"{reporter} data ends.")

    key = f"{prefix}:{vol}"
    volume = store.query(_VOLUME, {"key": key})
    if not volume:
        return _unverifiable(cite, f"Redline has no page map for volume {vol} of {reporter}.")
    volume = volume[0]
    vol_node = {"id": key, "label": f"{vol} {reporter}", "cite": f"{vol} {reporter}", "year": None, "role": "volume"}

    at_page = store.query(_AT_PAGE, {"key": key, "page": page})
    starts = [] if cite.get("short") else [c for c in at_page if c["first_page"] == page]
    for case in starts:
        if names_agree(cite, _names(case)):
            return _verified(store, cite, case, _warnings(cite, case), as_of=as_of)
    raw_name = cite["name"] or cite.get("short_name")
    # A name read from the brief itself, not guessed. "In re" captions don't count: the data names those
    # cases by their parties.
    named = bool(cite["name"] or cite.get("short_name")) and not is_caption(_cited(cite))
    elsewhere = []  # for a short form: the named case, found at another place in this volume
    if named and (cite.get("short") or not cite["name"]):
        words = [w.strip(",.") for w in cite["short_name"].split() if len(w.strip(",.")) > 3 and w[0].isupper()
                 and name_tokens(w)][:1]
        if not _readings(cite):
            words = []  # nothing comparable in the name: no evidence either way
        if words:
            elsewhere = [h for h in store.query(_NAMED_IN_VOLUME_PAGES, {"key": key, "word": words[0].lower()})
                         if names_agree(cite, _names(h)) and not (h["first_page"] <= page <= h["last_page"])]
        # A short name that matches no other case may be a nickname or a relator ("Newell" for
        # "United States ex rel. Newell v. City of St. Paul"): not proof of anything.
        named = bool(elsewhere)
    # A page can belong to two cases: the last page of one opinion and the first of the next.
    agreeing = [c for c in at_page if names_agree(cite, _names(c))] if _readings(cite) else []
    if raw_name and not named and at_page and not agreeing:
        case = (starts or at_page)[0]
        return _unverifiable(cite, f"Page {page} of {vol} {reporter} is in {_short(case)}. Redline cannot match "
                                   f"\"{raw_name}\" to that case: it may be a short name, a relator or an \"In re\" "
                                   f"caption the data does not use, so the citation is not called fabricated.")
    if at_page and not starts and not agreeing and not cite.get("short") and not named:
        case = at_page[0]  # "affirmed, 148 F.3d 1348": a full citation should give a first page
        return _unverifiable(cite, f"Page {page} of {vol} {reporter} is inside {_short(case)}, which starts at page "
                                   f"{case['first_page']}. Without a case name Redline cannot tell whether this is a "
                                   f"pin cite to that case or a wrong citation.")
    if at_page and not starts and (not named or agreeing):
        case = (agreeing or at_page)[0]  # a pin cite: "Havens Realty Corp., 455 U.S. 366" or "Fowler, 344 F.3d at 1211"
        note = [] if cite.get("short") else [f"Cited at page {page}, inside the case, which starts at page {case['first_page']}."]
        return _verified(store, cite, case, _warnings(cite, case) + note, as_of=as_of)
    if starts and not named:
        return _verified(store, cite, starts[0], _warnings(cite, starts[0]), as_of=as_of)

    # Everything below would call the citation fabricated. Only a page map that agrees with how courts
    # cite this volume can prove that.
    if page in set(volume["cited_starts"] or []):
        return _unverifiable(cite, f"Courts cite a case starting on page {page} of {vol} {reporter}, but Redline's "
                                   f"data has no case starting there, so this citation cannot be checked.")
    if not volume["complete"]:
        return _unverifiable(cite, f"Redline's page map for volume {vol} of {reporter} disagrees with how courts cite "
                                   f"it, so Redline does not prove fabrications in this volume.")

    if starts and page in set(volume["order_pages"] or []):
        return _unverifiable(cite, f"Page {page} of {vol} {reporter} holds several short orders; Redline cannot tell "
                                   f"which one is meant.")
    if starts:
        case = starts[0]
        return _fabricated(cite, "wrong_name",
                           f"{vol} {reporter} {page} is {_short(case)}, not the case named in the brief "
                           f"(\"{cite['name']}\").",
                           [vol_node, _evidence_case(case, "actual")],
                           [{"source": key, "target": case["id"], "type": "CONTAINS"}],
                           query=_query(_AT_PAGE, key=key, page=page))

    strictly_inside = [c for c in at_page if c["first_page"] < page < c["last_page"]]
    if at_page and not strictly_inside:
        case = at_page[0]  # a shared boundary page: the next opinion may start here, missing from the data
        return _unverifiable(cite, f"Page {page} of {vol} {reporter} is the last page of {_short(case)}; another "
                                   f"opinion may begin on the same page, so Redline cannot tell.")
    if at_page:
        case = strictly_inside[0]
        missing = ""
        words = [w.strip(",.") for w in (cite["name"] or cite.get("short_name", "")).split()
                 if len(w.strip(",.")) > 3 and w[0].isupper() and w.strip(",.").lower() not in {"united", "states"}][:1]
        if words:
            any_word = store.query(_NAMED_IN_VOLUME, {"key": key, "word": words[0].lower()})
            hits = [h for h in any_word if names_agree(cite, h["name"])]
            if not any_word:
                missing = f" No case named {words[0]} is in volume {vol}."
            elif not hits:
                missing = f" No case matching \"{cite['name'] or cite.get('short_name')}\" is in volume {vol}."
            else:
                missing = f" {hits[0]['name']} is {hits[0]['cite']}."
        return _fabricated(cite, "inside_other_case",
                           f"Page {page} of {vol} {reporter} is inside {_short(case)}, which runs from page "
                           f"{case['first_page']} to {case['last_page']}.{missing}",
                           [vol_node, _evidence_case(case, "actual")],
                           [{"source": key, "target": case["id"], "type": "CONTAINS"}],
                           query=_query(_AT_PAGE, key=key, page=page))

    if page > volume["last_page"]:
        printed = ("order lists, such as certiorari denials" if reporter == "U.S." else
                   "tables of decisions without published opinions")
        return _unverifiable(cite, f"Page {page} is after the last opinion in volume {vol} of {reporter} "
                                   f"(page {volume['last_page']}). {printed.capitalize()} are printed there and are not "
                                   f"in Redline's data.")
    if page in set(volume["order_pages"] or []):
        return _unverifiable(cite, f"Page {page} of {vol} {reporter} holds a short order (such as certiorari "
                                   f"denied), which Redline does not store as a case.")
    return _unverifiable(cite, f"No case in Redline's data begins or runs on page {page} of {vol} {reporter}. It may "
                               f"be a table of decisions without published opinions, which Redline does not hold.")


def check(store, text, as_of=None):
    """Check every citation in `text`. `as_of` (a year) asks whether each case was good law then."""
    results = [verify(store, c, as_of) for c in extract(text)]
    summary = {"citations": len(results), "verified": 0, "fabricated": 0, "unverifiable": 0,
               "overruled": 0, "caution": 0}
    for r in results:
        summary[r["verdict"].lower()] += 1
        if r["status"] in ("overruled", "overruled in part"):
            summary["overruled"] += 1
        elif r["status"] == "caution":
            summary["caution"] += 1
    return {"summary": summary, "as_of": as_of, "citations": results}
