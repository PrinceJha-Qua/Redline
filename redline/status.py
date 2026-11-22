"""Is a verified case still good law, and what does it stand on?

overruled  the case itself was overruled (explicit OVERRULES edge)
caution    the case relies on a case that was later overruled: it cites one directly, more than in
           passing (see relies_on), and was decided before that overruling
good law   neither, in Redline's data. A passing mention of a later-overruled case is reported in
           `mentions` but does not make a case yellow: United States v. Lopez (Commerce Clause) cites
           Planned Parenthood v. Casey once, and does not rest on it.
"""
import re

LIMIT = 5

_OVERRULED_BY = """
MATCH (o:Case)-[r:OVERRULES]->(c:Case {id: $id})
RETURN o.id AS id, o.name AS name, o.cite AS cite, o.year AS year, r.partial AS partial, r.topic AS topic
ORDER BY o.year
"""

# One hop out from the cited case to a case that was overruled after the cited case was decided,
# by some other case (Brown cites Plessy because Brown overruled it).
STANDS_ON = """
MATCH (c:Case {id: $id})-[r:CITES]->(m:Case)<-[o:OVERRULES]-(by:Case)
WHERE m.status IS NOT NULL AND by.year >= c.year AND by.id <> c.id
RETURN m.id AS id, m.name AS name, m.cite AS cite, m.year AS year, m.status AS status,
       r.weight AS weight, r.parenthetical AS parenthetical,
       by.id AS by_id, by.name AS by_name, by.cite AS by_cite, by.year AS by_year
ORDER BY r.weight DESC, by.year DESC
"""


# CAP counts every citation string, parallel citations included: an F.3d opinion citing a Supreme
# Court case once usually scores 3 (U.S., S.Ct., L.Ed.), a Supreme Court opinion 1.
SINGLE_MENTION = {"F3d": 3, "US": 1}
_NOISE = re.compile(r"^\s*(quoting|citing|see|cf\.)\b|omitted|emphasis|alteration|brackets|quotation|internal", re.I)


def relies_on(case_id, weight, parenthetical):
    """More than one citation, or a parenthetical saying what the case was cited for."""
    if parenthetical and not _NOISE.search(parenthetical):
        return True
    return (weight or 0) > SINGLE_MENTION.get(case_id.split(":")[0], 1)


def status_of(store, case):
    overruled_by = store.query(_OVERRULED_BY, {"id": case["id"]})
    chains, mentions, seen = [], [], set()
    for row in store.query(STANDS_ON, {"id": case["id"]}):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        (chains if relies_on(case["id"], row["weight"], row["parenthetical"]) else mentions).append({
            "case": {"id": row["id"], "name": row["name"], "cite": row["cite"], "year": row["year"],
                     "status": row["status"]},
            "weight": row["weight"], "parenthetical": row["parenthetical"],
            "overruled_by": {"id": row["by_id"], "name": row["by_name"], "cite": row["by_cite"], "year": row["by_year"]},
        })
    if overruled_by:
        full = [o for o in overruled_by if not o["partial"]]
        label = "overruled" if full else "overruled in part"
        first = (full or overruled_by)[0]
        reason = f"{label.capitalize()} by {first['name']}, {first['cite']} ({first['year']})."
        return {"status": label, "reason": reason, "overruled_by": overruled_by, "stands_on": chains[:LIMIT],
                "mentions": mentions[:LIMIT]}
    if chains:
        top = chains[0]
        more = f" and {len(chains) - 1} other overruled case{'s' if len(chains) > 2 else ''}" if len(chains) > 1 else ""
        reason = (f"Relies on {top['case']['name']}, {top['case']['cite']}{more}, "
                  f"later overruled by {top['overruled_by']['name']} ({top['overruled_by']['year']}).")
        return {"status": "caution", "reason": reason, "overruled_by": [], "stands_on": chains[:LIMIT],
                "stands_on_total": len(chains), "mentions": mentions[:LIMIT]}
    reason = "No overruling found in Redline's data."
    if mentions:
        m = mentions[0]
        reason += (f" It mentions {m['case']['name']} once in passing (later overruled by "
                   f"{m['overruled_by']['name']}, {m['overruled_by']['year']}); a single mention is not counted as reliance.")
    return {"status": "good law", "reason": reason, "overruled_by": [], "stands_on": [], "mentions": mentions[:LIMIT]}
