"""Tools for a drafting agent: find real authority instead of recalling it, repair a bad citation,
and ask what a brief would lose if a case were overruled.

find_authority   a proposition -> the cases courts have cited for it, in the courts' own words
                 (the parentheticals on CITES edges: "(holding that temporal proximity alone ...)"),
                 and the appeals-court opinions that said so
did_you_mean     a case name -> the real cases with that name, and where they are reported
related          cases courts cite together with the given ones (co-citation, Salton's cosine)
what_if          overrule a case inside a Relate transaction on the read-only store, measure who relied
                 on it and re-check a brief with the same code, then roll back

Every answer is a graph query. Nothing is generated.
"""
import math
import re

from .citations import extract
from .status import relies_on, status_of
from .verify import check

_STOP = set("""a about above after again against all also although an and any are as at be because been before
being below between both but by can could did do does doing down during each either even every few for from further
had has have having here how however if in into is it its itself just may might more most must no nor not now of off
on once only or other our out over own same shall should so some such than that the their them then there these they
this those through to too under until up upon very was were what when where whether which while who whom why will
with within without would court courts case cases held holding hold holds finding noting""".split())

_CIRCUITS = {"first": "1st", "second": "2d", "third": "3d", "fourth": "4th", "fifth": "5th", "sixth": "6th",
             "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th", "eleventh": "11th",
             "dc": "D.C.", "d.c.": "D.C.", "federal": "Fed.", "fed": "Fed."}


def court_label(circuit):
    """"Third", "3rd", "3d Cir." or "3" -> "3d Cir." (the court field in the store)."""
    if not circuit:
        return None
    c = circuit.strip().lower().replace(" circuit", "").replace(" cir.", "").replace(" cir", "").strip()
    if c in _CIRCUITS:
        return f"{_CIRCUITS[c]} Cir."
    m = re.match(r"(\d{1,2})", c)
    if m:
        n = int(m.group(1))
        return f"{n}{'st' if n == 1 else 'd' if n in (2, 3) else 'th'} Cir."
    return circuit


def _terms(text):
    words = re.findall(r"[A-Za-z][A-Za-z\-]+", text or "")
    return list(dict.fromkeys(w.lower() for w in words if len(w) > 2 and w.lower() not in _STOP))


_FIND = """
CALL db.index.fulltext.queryRelationships('cites_parenthetical', $q) YIELD relationship AS r, score
WITH r, score ORDER BY score DESC LIMIT $pool
MATCH (a:Case)-[r]->(b:Case)
RETURN a.id AS a_id, a.name AS a_name, a.cite AS a_cite, a.court AS a_court, a.year AS a_year,
       b.id AS id, b.name AS name, b.cite AS cite, b.court AS court, b.year AS year, b.cited_by AS cited_by,
       r.parenthetical AS parenthetical, score
"""


def find_authority(store, proposition, circuit=None, limit=5, as_of=None):
    """Cases courts have cited for `proposition`, ranked by how well and how often the courts' own
    descriptions match it. With `circuit`, that circuit's descriptions come first, and its opinions are
    returned as circuit authority."""
    terms = _terms(proposition)
    if not terms:
        return {"proposition": proposition, "authorities": [], "circuit_opinions": [], "query": None}
    court = court_label(circuit)
    params = {"q": " OR ".join(terms), "pool": 300}
    rows = store.query(_FIND, params)
    if as_of:
        rows = [r for r in rows if (r["a_year"] or 0) <= as_of and (r["year"] or 0) <= as_of]
    by_case = {}
    for r in rows:
        e = by_case.setdefault(r["id"], {"case": {k: r[k] for k in ("id", "name", "cite", "court", "year")},
                                         "cited_by": r["cited_by"], "score": 0.0, "described_as": []})
        e["score"] += r["score"] * (1.5 if court and r["a_court"] == court else 1.0)
        e["described_as"].append({"by": {"id": r["a_id"], "name": r["a_name"], "cite": r["a_cite"],
                                         "court": r["a_court"], "year": r["a_year"]},
                                  "parenthetical": r["parenthetical"], "score": round(r["score"], 2)})
    ranked = sorted(by_case.values(), key=lambda e: -e["score"])[:limit]
    for e in ranked:
        st = status_of(store, e["case"], as_of)
        e["status"], e["status_reason"] = st["status"], st["reason"]
        e["described_as"].sort(key=lambda d: (d["by"]["court"] != court, -d["score"]))
        e["described_as"] = e["described_as"][:3]
        e["score"] = round(e["score"], 1)
    # Good law first: an agent should not be handed an overruled case as its best authority.
    ranked.sort(key=lambda e: (e["status"] in ("overruled", "overruled in part"), -e["score"]))
    opinions = []
    if court:
        seen = set()
        for r in sorted(rows, key=lambda r: -r["score"]):
            if r["a_court"] == court and r["a_id"] not in seen:
                seen.add(r["a_id"])
                opinions.append({"case": {"id": r["a_id"], "name": r["a_name"], "cite": r["a_cite"],
                                          "court": r["a_court"], "year": r["a_year"]},
                                 "said": r["parenthetical"], "citing": f"{r['name']}, {r['cite']}"})
        opinions = opinions[:limit]
    return {"proposition": proposition, "circuit": court, "as_of": as_of, "authorities": ranked,
            "circuit_opinions": opinions,
            "note": "Each authority is described in the words of the courts that cited it. Read the case before "
                    "relying on it: a parenthetical is a court's summary, not the holding itself.",
            "query": {"cypher": " ".join(_FIND.split()), "params": params}}


_GENERIC = {"inc", "corp", "corporation", "company", "insurance", "ins", "mutual", "services", "service", "serv",
            "national", "nat'l", "natl", "united", "states", "america", "american", "metro", "metropolitan", "prop",
            "property", "cas", "casualty", "fire", "assn", "association", "bank", "group", "holdings", "the", "and",
            "llc", "ltd", "dept", "department", "county", "city", "state", "board", "commission", "fed", "federal",
            "people", "commissioner", "secretary", "director", "warden", "attorney", "general"}

_BY_NAME = """
CALL db.index.fulltext.queryNodes('case_name', $q) YIELD node, score
RETURN node.id AS id, node.name AS name, node.cite AS cite, node.court AS court, node.year AS year,
       node.status AS status, node.cited_by AS cited_by
LIMIT 300
"""


def _distinct(party):
    words = [w.strip(".,'").lower() for w in re.findall(r"[A-Za-z][A-Za-z'.]+", party)]
    return sorted({w for w in words if len(w) >= 4 and w.isalpha() and w not in _GENERIC}, key=lambda w: (-len(w), w))[:2]


_SUFFIX = {"inc", "co", "corp", "corporation", "company", "llc", "ltd", "the", "and", "of", "for", "et", "al", "v", "vs"}


def _words(name):
    name = re.sub(r"\b(?:[A-Za-z]\.\s?){2,}", lambda m: re.sub(r"[.\s]", "", m.group()) + " ", name or "")
    return [w for w in (x.strip(".,'()").lower() for x in re.findall(r"[A-Za-z][A-Za-z'.]*", name))
            if w and w not in _SUFFIX]


def _abbreviates(short, word):
    """"natl" abbreviates "national", "telecomms" "telecommunications": same first letter, and the
    short form's letters appear in order."""
    short, word = short.replace("'", "").replace(".", ""), word.replace("'", "").replace(".", "")
    if not short or not word or short[0] != word[0]:
        return False
    it = iter(word)
    return all(ch in it for ch in short)


def _covers(candidate, words):
    """Every word of the cited name appears in the candidate's name, in full or abbreviated."""
    have = _words(candidate)
    return all(any(_abbreviates(w, h) or _abbreviates(h, w) for h in have) for w in words if len(w) >= 3)


def _same_parties(parties, candidate):
    """Each side of the cited "v." matches the same side of the candidate's name."""
    theirs = [p for p in re.split(r"\s+v\.?\s+", candidate or "") if p.strip()]
    if len(parties) != len(theirs):
        return len(parties) == 1 and _covers(candidate, _words(parties[0]))
    return all(_covers(t, _words(p)) for p, t in zip(parties, theirs))


def did_you_mean(store, name, exclude=None, limit=3):
    """Real cases whose names carry the distinctive words of each party in `name`. A name made only of
    generic words ("Metro. Prop. & Cas. Ins. Co.") is not looked up: it would match the wrong case."""
    parties = [p for p in re.split(r"\s+v\.?\s+", name or "") if p.strip()][:2]
    per_party = [_distinct(p) for p in parties]
    if not per_party or not all(per_party):
        return []
    words = [w for ws in per_party for w in ws]
    # prefixes, so an abbreviation in the brief ("Telecomms.") still finds the full name
    rows = store.query(_BY_NAME, {"q": " AND ".join(w[:4] + "*" for w in words)})
    same = [h for h in rows if h["cite"] != exclude and _same_parties(parties, h["name"])]
    if len(same) > 5:  # "Smith v. Jones": many real cases fit, so any one of them would be a guess
        return []
    same.sort(key=lambda h: -(h["cited_by"] or 0))
    return same[:limit]


_RELATED = """
MATCH (x:Case)<-[:CITES]-(b:Case)-[:CITES]->(s:Case)
WHERE x.id IN $ids AND NOT s.id IN $ids
WITH s, count(DISTINCT b) AS together
WHERE together >= 2
RETURN s.id AS id, s.name AS name, s.cite AS cite, s.court AS court, s.year AS year, s.status AS status,
       s.cited_by AS cited_by, together
ORDER BY together DESC LIMIT 200
"""


def related(store, case_ids, limit=5):
    """Cases courts cite together with `case_ids`: co-citation normalised by Salton's cosine, so a case
    cited everywhere (Celotex, Anderson v. Liberty Lobby) does not crowd out the specific ones."""
    ids = [i for i in case_ids if i][:20]
    if not ids:
        return []
    base = store.query("MATCH (x:Case) WHERE x.id IN $ids RETURN sum(x.cited_by) AS n", {"ids": ids})[0]["n"] or 1
    rows = store.query(_RELATED, {"ids": ids})
    for r in rows:
        r["cosine"] = round(r["together"] / math.sqrt(base * max(r["cited_by"] or 1, 1)), 4)
    rows = [r for r in rows if r["status"] is None]  # never suggest an overruled case
    return sorted(rows, key=lambda r: -r["cosine"])[:limit]


def what_if(store, case_id, text=None, year=2026):
    """Overrule `case_id` hypothetically and report what changes: how many decisions rely on it, by
    court, and, given a brief, which of its citations change status. Runs inside a transaction on the
    read-only store that Relate will not commit; Redline rolls it back."""
    target = store.query("MATCH (c:Case {id: $id}) RETURN c.id AS id, c.name AS name, c.cite AS cite, "
                         "c.year AS year, c.status AS status", {"id": case_id})
    if not target:
        return None
    target = target[0]
    hyp = {"id": "HYPOTHETICAL", "name": "Hypothetical overruling", "cite": "(hypothetical)", "year": year}
    writes = [("MATCH (x:Case {id: $id}) SET x.status = coalesce(x.status, 'overruled') "
               "CREATE (:Case {id: $h, name: $name, cite: $cite, year: $year})-[:OVERRULES {partial: false, "
               "topic: 'hypothetical'}]->(x)", {"id": case_id, "h": hyp["id"], "name": hyp["name"],
                                               "cite": hyp["cite"], "year": year})]
    before = check(store, text) if text else None

    def measure():
        citing = store.query("MATCH (c:Case)-[r:CITES]->(x:Case {id: $id})<-[:OVERRULES]-(:Case {id: $h}) "
                             "RETURN c.id AS id, c.name AS name, c.cite AS cite, c.court AS court, c.year AS year, "
                             "r.weight AS weight, r.parenthetical AS parenthetical", {"id": case_id, "h": hyp["id"]})
        after = check(store, text) if text else None
        return citing, after

    citing, after = store.hypothetical(writes, measure)
    relying = [c for c in citing if relies_on(c["id"], c["weight"], c["parenthetical"])]
    by_court = {}
    for c in relying:
        by_court[c["court"]] = by_court.get(c["court"], 0) + 1
    changed = []
    if text:
        for b, a in zip(before["citations"], after["citations"]):
            if b["status"] != a["status"]:
                changed.append({"text": a["text"], "before": b["status"], "after": a["status"], "reason": a["reason"]})
    still = store.query("MATCH (h:Case {id: $h}) RETURN count(h) AS n", {"h": hyp["id"]})[0]["n"]
    return {"case": target, "citing": len(citing), "relying": len(relying),
            "relying_by_court": dict(sorted(by_court.items(), key=lambda kv: -kv[1])),
            "examples": sorted(relying, key=lambda c: -(c["weight"] or 0))[:5],
            "brief": {"changed": changed, "citations": len(after["citations"])} if text else None,
            "rolled_back": still == 0,
            "how": "Ran inside a Relate transaction on the read-only store: the overruling was written, every "
                   "query and the brief check ran against it, and the transaction was rolled back."}


def suggest_for(store, result):
    """Attach repairs to a checked brief: for each fabricated citation, the real cases with that name."""
    for c in result["citations"]:
        if c["verdict"] == "FABRICATED" and c.get("name"):
            c["suggestions"] = did_you_mean(store, c["name"], exclude=None)
    return result


def citations_in(text):
    return [c["text"] for c in extract(text)]
