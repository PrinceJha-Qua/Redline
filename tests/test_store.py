"""Phase 1: the committed store holds the facts the checker depends on."""
import pytest

from redline.store import Store


@pytest.fixture(scope="module")
def store():
    s = Store()
    yield s
    s.close()


def one(store, q, **params):
    rows = store.query(q, params)
    assert len(rows) == 1, rows
    return rows[0]


def test_reporters_cover_full_runs(store):
    rows = {r["abbr"]: r for r in store.query("MATCH (r:Reporter) RETURN r.abbr AS abbr, r.first_vol AS first, "
                                               "r.last_vol AS last, r.volumes AS volumes, r.complete AS complete")}
    assert rows["U.S."] == {"abbr": "U.S.", "first": 1, "last": 572, "volumes": 572, "complete": True}
    assert rows["F.3d"] == {"abbr": "F.3d", "first": 1, "last": 935, "volumes": 935, "complete": True}


def test_varghese_page_belongs_to_another_case(store):
    # Mata v. Avianca: "Varghese v. China Southern Airlines, 925 F.3d 1339 (11th Cir. 2019)" was invented.
    hit = one(store, "MATCH (:Volume {key: 'F3d:925'})-[:CONTAINS]->(c:Case) "
                     "WHERE c.first_page <= $p AND c.last_page >= $p RETURN c.name AS name, c.court AS court", p=1339)
    assert hit == {"name": "J.D. v. Azar", "court": "D.C. Cir."}
    none = one(store, "MATCH (:Volume {key: 'F3d:925'})-[:CONTAINS]->(c:Case) "
                      "WHERE toLower(c.name) CONTAINS 'varghese' RETURN count(c) AS n")
    assert none["n"] == 0


def test_volume_knows_its_last_page(store):
    v = one(store, "MATCH (v:Volume {key: 'F3d:925'}) RETURN v.last_page AS last, v.cases AS cases")
    assert v == {"last": 1384, "cases": 116}


@pytest.mark.parametrize("overruled, overruling", [
    ("US:410:113", "Dobbs v. Jackson Women’s Health Organization"),
    ("US:467:837", "Loper Bright Enterprises v. Raimondo"),
    ("US:163:537", "Brown v. Board of Education"),
])
def test_overrulings(store, overruled, overruling):
    row = one(store, "MATCH (a:Case)-[:OVERRULES]->(b:Case {id: $id}) RETURN a.name AS by, b.status AS status",
              id=overruled)
    assert row == {"by": overruling, "status": "overruled"}


def test_parallel_citation_resolves(store):
    row = one(store, "MATCH (:Citation {text: '93 S.Ct. 705'})-[:CITATION_OF]->(c:Case) RETURN c.id AS id")
    assert row["id"] == "US:410:113"


def test_appeals_courts_rest_on_chevron(store):
    row = one(store, "MATCH (:Case {id: 'US:467:837'})<-[:CITES]-(a:Case {reporter: 'F.3d'}) RETURN count(a) AS n")
    assert row["n"] > 4000


def test_store_is_read_only(store):
    with pytest.raises(Exception):
        store.query("CREATE (:Case {id: 'should-not-exist'})")
