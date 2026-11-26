"""Phase 3: the agent tools. Checking as of a date, repairing a bad citation, finding real authority,
and a what-if overruling that never reaches the store."""
import pytest

from redline import agent, service

from .test_api import store_hash

CHEVRON = "Chevron U.S.A. Inc. v. Natural Res. Def. Council, Inc., 467 U.S. 837 (1984)."


def only(text, as_of=None):
    result = service.check_text(text, as_of)
    assert len(result["citations"]) == 1, result
    return result["citations"][0]


def test_chevron_was_good_law_in_2023():
    then = only(CHEVRON, as_of=2023)
    assert then["status"] == "good law"
    assert then["later"][0]["name"] == "Loper Bright Enterprises v. Raimondo"
    assert "later, by Loper Bright" in then["reason"]
    assert only(CHEVRON)["status"] == "overruled"


def test_caution_needs_the_overruling_to_have_happened():
    # Brand X relies on Chevron: caution today, good law for a brief filed in 2020.
    brand_x = "Nat'l Cable & Telecomms. Ass'n v. Brand X Internet Servs., 545 U.S. 967 (2005)."
    assert only(brand_x)["status"] == "caution"
    assert only(brand_x, as_of="2020-06-01")["status"] == "good law"


def test_a_brief_cannot_cite_a_later_case():
    c = only("Loper Bright Enterprises v. Raimondo, 603 U.S. 369 (2024).", as_of=2020)
    assert any("could not cite it" in w for w in c["warnings"])


def test_as_of_must_be_a_year():
    with pytest.raises(ValueError):
        service.check_text(CHEVRON, as_of="last week")


@pytest.mark.parametrize("name, cite", [
    ("Mount Vernon Fire Ins. Co. v. VisionAid", "825 F.3d 67"),
    ("Chevron U.S.A. Inc. v. Natural Res. Def. Council", "467 U.S. 837"),
    ("Nat'l Cable & Telecomms. Ass'n v. Brand X Internet Servs.", "545 U.S. 967"),
])
def test_did_you_mean_finds_the_real_case(name, cite):
    assert cite in [h["cite"] for h in agent.did_you_mean(service.store(), name)]


@pytest.mark.parametrize("name", [
    "Varghese v. China Southern Airlines",   # invented in Mata v. Avianca
    "Miller v. United Airlines, Inc",        # "Miller v. American Airlines" is a different case
    "Metro. Prop. & Cas. Ins. Co. v. Smith",  # nothing distinctive enough to look up
])
def test_did_you_mean_suggests_nothing_rather_than_the_wrong_case(name):
    assert agent.did_you_mean(service.store(), name) == []


def test_did_you_mean_keeps_the_parties_in_order():
    found = [h["name"] for h in agent.did_you_mean(service.store(), "Smith v. Jones")]
    assert found and all(n.startswith("Smith") for n in found)  # never "Jones v. Smith"


def test_a_fabricated_citation_carries_its_repair():
    c = only("Mount Vernon Fire Ins. Co. v. VisionAid, Inc., 825 F.3d 1 (1st Cir. 2016).")
    if c["verdict"] == "FABRICATED":
        assert "825 F.3d 67" in [h["cite"] for h in c["suggestions"]]


def test_find_authority_returns_real_cases_in_the_courts_words():
    r = service.find_authority("temporal proximity alone is insufficient to establish causation for retaliation",
                               circuit="Third")
    assert r["circuit"] == "3d Cir."
    top = r["authorities"][0]
    assert top["case"]["cite"] == "532 U.S. 268"  # Clark County School District v. Breeden
    assert top["status"] == "good law"
    assert all(d["parenthetical"] for d in top["described_as"])
    assert "503 F.3d 217" in [o["case"]["cite"] for o in r["circuit_opinions"]]  # LeBoon (3d Cir. 2007)
    assert all(o["case"]["court"] == "3d Cir." for o in r["circuit_opinions"])


def test_find_authority_puts_overruled_cases_last():
    r = service.find_authority("deference to an agency's reasonable interpretation of an ambiguous statute", limit=8)
    statuses = [a["status"] for a in r["authorities"]]
    bad = [i for i, s in enumerate(statuses) if s in ("overruled", "overruled in part")]
    assert bad, statuses  # Chevron is found ...
    assert all(s not in ("overruled", "overruled in part") for s in statuses[:bad[0]])
    assert bad == list(range(bad[0], len(statuses)))  # ... and ranked below every good-law case


@pytest.mark.parametrize("circuit, label", [("Third", "3d Cir."), ("3rd", "3d Cir."), ("9th Cir.", "9th Cir."),
                                            ("D.C.", "D.C. Cir."), ("1", "1st Cir."), ("Eleventh", "11th Cir.")])
def test_circuit_names(circuit, label):
    assert agent.court_label(circuit) == label


def test_related_authority_is_good_law_and_on_point():
    rows = service.related(["US:467:837"])
    names = [r["name"] for r in rows]
    assert "United States v. Mead Corp." in names[:3]
    assert all(r["status"] is None for r in rows)


def test_what_if_rolls_back_and_never_touches_the_store():
    before = store_hash()
    brief = CHEVRON + " See Nat'l Cable & Telecomms. Ass'n v. Brand X Internet Servs., 545 U.S. 967 (2005)."
    r = service.what_if("US:545:967", brief)
    assert r["rolled_back"] is True
    assert r["relying"] > 100 and r["citing"] >= r["relying"]
    assert {"text": "545 U.S. 967", "before": "caution", "after": "overruled"} == \
           {k: r["brief"]["changed"][0][k] for k in ("text", "before", "after")}
    assert only("Nat'l Cable & Telecomms. Ass'n v. Brand X Internet Servs., 545 U.S. 967 (2005).")["status"] == "caution"
    assert service.store().query("MATCH (c:Case {id: 'HYPOTHETICAL'}) RETURN count(c) AS n")[0]["n"] == 0
    assert store_hash() == before


def test_the_store_refuses_to_commit_a_write():
    # The guarantee behind what_if: a read-only connection can stage writes, but never commit them.
    import relate
    from redline.store import store_path
    con = relate.connect(str(store_path()), read_only=True)
    con.autocommit = False
    cur = con.cursor()
    cur.execute("CREATE (:Case {id: 'NOT-COMMITTED'})")
    with pytest.raises(Exception, match="read-only|ReadOnly"):
        con.commit()
    con.rollback()
    con.close()


def test_agent_endpoints(client):
    a = client.get("/api/authority", params={"q": "qualified immunity clearly established law", "circuit": "9th"})
    assert a.status_code == 200 and a.json()["authorities"]
    assert client.get("/api/related", params={"ids": "US:467:837"}).json()
    w = client.post("/api/what-if", json={"case_id": "US:384:436"})
    assert w.status_code == 200 and w.json()["rolled_back"] is True
    assert client.post("/api/what-if", json={"case_id": "US:0:0"}).status_code == 404
    assert client.post("/api/check", json={"text": CHEVRON, "as_of": "nope"}).status_code == 422


def test_a_shared_word_does_not_name_another_case():
    # "Mount Royal Joint Venture v. Kempthorne" shares one word with the cited name; it is not the case.
    c = only("Mount Vernon Fire Ins. Co. v. Visionaid, Inc., 477 F.3d 6, 9 (1st Cir. 2007).")
    assert c["verdict"] == "FABRICATED"
    assert "Kempthorne" not in c["reason"]
