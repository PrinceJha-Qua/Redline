"""The operations every surface shares: the HTTP API, the MCP tools and the command line."""
import re

from .status import status_of
from .store import Store
from .verify import check, coverage

_store = None
MAX_TEXT = 200_000


def store():
    global _store
    if _store is None:
        _store = Store()
    return _store


def check_text(text):
    if len(text) > MAX_TEXT:
        raise ValueError(f"The text is {len(text):,} characters; the limit is {MAX_TEXT:,}.")
    return check(store(), text)


def get_case(case_id):
    s = store()
    rows = s.query("MATCH (c:Case {id: $id}) OPTIONAL MATCH (c)-[:DECIDED_BY]->(k:Court) "
                   "RETURN c AS case, k.name AS court_name", {"id": case_id})
    if not rows:
        return None
    case = rows[0]["case"]
    case["court_name"] = rows[0]["court_name"]
    st = status_of(s, case)
    cites = s.query("MATCH (c:Case {id: $id})-[r:CITES]->(t:Case) RETURN t.id AS id, t.name AS name, t.cite AS cite, "
                    "t.year AS year, t.status AS status, r.weight AS weight, r.parenthetical AS parenthetical "
                    "ORDER BY r.weight DESC LIMIT 25", {"id": case_id})
    cited_by = s.query("MATCH (c:Case {id: $id})<-[r:CITES]-(f:Case) RETURN f.id AS id, f.name AS name, f.cite AS cite, "
                       "f.year AS year, f.court AS court, r.weight AS weight, r.parenthetical AS parenthetical "
                       "ORDER BY r.weight DESC, f.year DESC LIMIT 25", {"id": case_id})
    overrules = s.query("MATCH (c:Case {id: $id})-[r:OVERRULES]->(o:Case) RETURN o.id AS id, o.name AS name, "
                        "o.cite AS cite, o.year AS year, r.partial AS partial", {"id": case_id})
    return {"case": case, "status": st["status"], "reason": st["reason"], "overruled_by": st["overruled_by"],
            "overrules": overrules, "stands_on": st["stands_on"], "cites": cites, "cited_by": cited_by}


def search(q, limit=10):
    words = re.findall(r"[A-Za-z0-9]+", q or "")
    if not words:
        return []
    limit = max(1, min(int(limit), 50))
    query = ("CALL db.index.fulltext.queryNodes('case_name', $q) YIELD node, score "
             "RETURN node.id AS id, node.name AS name, node.cite AS cite, node.court AS court, node.year AS year, "
             "node.status AS status, node.cited_by AS cited_by, score "
             "ORDER BY node.cited_by DESC, score DESC LIMIT $limit")  # the most-cited match first: "Chevron" means Chevron
    rows = store().query(query, {"q": " AND ".join(words), "limit": limit})
    return rows or store().query(query, {"q": " OR ".join(words), "limit": limit})


def get_coverage():
    s = store()
    meta = s.query("MATCH (m:Meta) RETURN m AS meta")[0]["meta"]
    return {"engine": "Relate", "store": str(s.path), "pack": meta["pack"], "built": meta["built"],
            "cases": meta["cases"], "citations": meta["citations"], "overrulings": meta["overrulings"],
            "reporters": list(coverage(s).values()), "sources": meta["sources"],
            "verdicts": {"VERIFIED": "The case exists. Status: good law, caution or overruled.",
                         "FABRICATED": "Points into a volume Redline holds in full, and cannot be right.",
                         "UNVERIFIABLE": "Outside Redline's coverage. Never called fake."}}
