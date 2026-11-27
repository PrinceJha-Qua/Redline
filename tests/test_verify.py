"""Phase 2: every fixture brief gets the verdicts a careful reader would give it."""
from pathlib import Path

import pytest

from redline import service
from redline.citations import extract, names_agree

BRIEFS = Path(__file__).parent / "fixtures" / "briefs"

# (citation text, verdict, status) in the order they appear
EXPECTED = {
    "mata.txt": [
        ("925 F.3d 1339", "FABRICATED", None),
        ("2013 IL App (1st) 111279-U", "UNVERIFIABLE", None),
        ("905 F. Supp. 2d 121", "UNVERIFIABLE", None),
        ("2019 WL 4639462", "UNVERIFIABLE", None),
        ("2017 WL 2418825", "UNVERIFIABLE", None),
        ("174 F.3d 366", "FABRICATED", None),
        ("516 U.S. 217", "VERIFIED", "good law"),
        ("525 U.S. 155", "VERIFIED", "good law"),
    ],
    "chevron.txt": [
        ("467 U.S. 837", "VERIFIED", "overruled"),
        ("569 U.S. 290", "VERIFIED", "caution"),
        ("920 F.3d 999", "VERIFIED", "caution"),
        ("935 F.3d 1148", "VERIFIED", "caution"),
        ("603 U.S. 369", "VERIFIED", "good law"),
    ],
    "mixed.txt": [
        ("477 U.S. 317", "VERIFIED", "good law"),
        ("163 U.S. 537", "VERIFIED", "overruled"),
        ("410 U.S. 113", "VERIFIED", "overruled"),
        ("93 S. Ct. 705", "VERIFIED", "overruled"),
        ("347 U.S. 483", "FABRICATED", None),
        ("925 F.3d 1500", "UNVERIFIABLE", None),
        ("14 Cal. 4th 155", "UNVERIFIABLE", None),
        ("603 U.S. 279", "UNVERIFIABLE", None),
        ("477 U.S. 242", "VERIFIED", "good law"),
    ],
    "state.txt": [
        ("14 Cal. 4th 155", "UNVERIFIABLE", None),
        ("13 Cal. 3d 804", "UNVERIFIABLE", None),
        ("248 N.Y. 339", "UNVERIFIABLE", None),
        ("133 S.W.3d 217", "UNVERIFIABLE", None),
    ],
    "clean.txt": [
        ("550 U.S. 544", "VERIFIED", "good law"),
        ("556 U.S. 662", "VERIFIED", "good law"),
        ("516 U.S. 217", "VERIFIED", "good law"),
        ("477 U.S. 317", "VERIFIED", "good law"),
        ("174 F.3d 352", "VERIFIED", "good law"),
    ],
}


def by_text(result, text):
    return next(c for c in result["citations"] if c["text"] == text)


@pytest.mark.parametrize("brief", sorted(EXPECTED))
def test_fixture_verdicts(brief):
    result = service.check_text((BRIEFS / brief).read_text())
    got = [(c["text"], c["verdict"], c["status"]) for c in result["citations"]]
    assert got == EXPECTED[brief]


def test_varghese_reason_names_the_real_case():
    c = by_text(service.check_text((BRIEFS / "mata.txt").read_text()), "925 F.3d 1339")
    assert c["problem"] == "inside_other_case"
    assert "J.D. v. Azar" in c["reason"] and "1291 to 1349" in c["reason"]
    assert "No case named Varghese is in volume 925" in c["reason"]


def test_wrong_name_on_a_real_page():
    c = by_text(service.check_text((BRIEFS / "mixed.txt").read_text()), "347 U.S. 483")
    assert c["problem"] == "wrong_name" and "Brown v. Board of Education" in c["reason"]


def test_past_last_page_is_not_proof():
    # F.3d prints tables of unpublished decisions after the opinions ("McZeal v. Ocwen, 252 F.3d 1355")
    c = by_text(service.check_text((BRIEFS / "mixed.txt").read_text()), "925 F.3d 1500")
    assert c["verdict"] == "UNVERIFIABLE" and "page 1384" in c["reason"]


@pytest.mark.parametrize("text", [
    "These cases follow principles established in BMW v. Gore. 312 F.3d 998, 1013-14 (9th Cir.2002).",
    "in accord with our decisions in Nardello and Taylor v. United States, 495 U. S. 575 (1990).",
    "its willingness to reconsider. If Harris v. United States, 536 U.S. 545 (2002), falls",
    "the Juvenile Delinquency Act. United States v. JJ, 704 F.3d 1219 (9th Cir. 2013).",
    "Petitioners at 13, Kennecott, 88 F.3d 1191 (No. 93-1700).",
    "See Kasalo v. Harris & Harris, Ltd., 656 F.3d 557, 561 (7th Cir. 2011).",
])
def test_real_citations_from_unseen_opinions(text):
    assert service.check_text(text)["citations"][0]["verdict"] != "FABRICATED"


def test_caution_carries_the_chain():
    c = by_text(service.check_text((BRIEFS / "chevron.txt").read_text()), "920 F.3d 999")
    top = c["stands_on"][0]
    assert top["case"]["id"] == "US:467:837"
    assert top["overruled_by"]["name"].startswith("Loper Bright")
    assert {e["type"] for e in c["evidence"]["edges"]} == {"CITES", "OVERRULES"}


def test_case_that_rests_on_roe_and_casey():
    c = service.check_text("J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019).")["citations"][0]
    assert c["status"] == "caution"
    assert {ch["case"]["id"] for ch in c["stands_on"]} >= {"US:505:833", "US:410:113"}


def test_overruling_case_is_not_flagged_for_what_it_overruled():
    c = service.check_text("Brown v. Board of Education, 347 U.S. 483 (1954).")["citations"][0]
    assert c["status"] == "good law"


def test_pin_cite_outside_the_case_is_a_warning_not_a_fabrication():
    c = by_text(service.check_text((BRIEFS / "mixed.txt").read_text()), "477 U.S. 242")
    assert c["verdict"] == "VERIFIED" and any("Pin cite 900" in w for w in c["warnings"])


def test_short_forms_are_checked_against_the_page_they_name():
    text = "Chevron U.S.A. Inc. v. NRDC, 467 U.S. 837 (1984). Id. at 842. Chevron, 467 U.S. at 843."
    assert [c["text"] for c in extract(text)] == ["467 U.S. 837", "467 U.S. at 843"]  # "Id." carries no volume
    short = service.check_text(text)["citations"][1]
    assert short["verdict"] == "VERIFIED" and short["case"]["id"] == "US:467:837"


def test_short_form_pointing_at_another_case():
    c = service.check_text("States may not execute them. Atkins, 536 U.S. 14.")["citations"][0]
    assert c["verdict"] == "FABRICATED" and "Atkins v. Virginia is 536 U.S. 304" in c["reason"]


def test_relator_matches_through_the_full_caption():
    # "Newell" is the relator in United States ex rel. Newell v. City of St. Paul; the short name drops him
    c = service.check_text("as the court held. Newell, 728 F.3d at 799.")["citations"][0]
    assert c["verdict"] == "VERIFIED" and c["case"]["id"] == "F3d:728:791"


def test_unmatched_short_name_is_not_called_fake():
    c = service.check_text("the claimed apparatus. Fowler, 344 F.3d at 1211.")["citations"][0]
    assert c["verdict"] == "UNVERIFIABLE"


def test_in_re_caption_is_not_called_fake():
    c = service.check_text("In re Lupron Mktg. & Sales Practices Litig., 677 F.3d 21, 38 (1st Cir. 2012).")["citations"][0]
    assert c["verdict"] == "VERIFIED"


@pytest.mark.parametrize("text, problem", [
    ("Smith v. Jones, 982 N.E.4th 701 (1st Cir. 1981).", "no_such_series"),
    ("Doe v. Roe, 475 F.3d 972 (8th Cir. 1983).", "series_not_in_print"),
])
def test_impossible_series(text, problem):
    c = service.check_text(text)["citations"][0]
    assert c["verdict"] == "FABRICATED" and c["problem"] == problem


def test_a_page_number_in_a_parenthetical_is_not_a_year():
    c = service.check_text("Fisher, 584 F.3d at 894 (citing Graham, 490 U.S. at 395, 109 S.Ct. 1865).")["citations"][0]
    assert c["verdict"] != "FABRICATED"


@pytest.mark.parametrize("cited, actual", [
    ("Chevron U.S.A. Inc. v. NRDC", "Chevron U. S. A. Inc. v. Natural Resources Defense Council, Inc."),
    ("Southwestern Elec. Power Co. v. EPA", "Southwestern Elec. Power Co. v. U.S. E.P.A."),
    ("Zicherman v. Korean Air Lines Co.", "Zicherman ex rel. Estate of Kole v. Korean Air Lines Co."),
    ("Perez-Sanchez v. U.S. Att'y Gen.", "Perez-Sanchez v. U.S. Attorney Gen."),
    ("", "Anything v. Anyone"),
])
def test_names_agree(cited, actual):
    assert names_agree(cited, actual)


@pytest.mark.parametrize("cited, actual", [
    ("Varghese v. China Southern Airlines", "J.D. v. Azar"),
    ("Smith v. Jones", "Chevron U. S. A. Inc. v. Natural Resources Defense Council, Inc."),
])
def test_names_disagree(cited, actual):
    assert not names_agree(cited, actual)


@pytest.mark.parametrize("text", ["", "   ", "\n\n", "No citations here at all."])
def test_text_without_citations(text):
    assert service.check_text(text) == {"summary": {"citations": 0, "verified": 0, "fabricated": 0, "unverifiable": 0,
                                                    "overruled": 0, "caution": 0}, "as_of": None, "citations": []}


def test_a_passing_mention_is_not_reliance():
    # Lopez (Commerce Clause) cites Casey once, with no parenthetical: noted, not flagged.
    c = service.check_text("United States v. Lopez, 514 U.S. 549 (1995).")["citations"][0]
    assert c["status"] == "good law"
    assert "US:505:833" in {m["case"]["id"] for m in c["mentions"]}
    assert "passing" in c["reason"]


def test_reliance_rule():
    from redline.status import relies_on
    assert not relies_on("F3d:1:1", 3, None)            # one citation with its parallel cites
    assert relies_on("F3d:1:1", 6, None)                # cited twice
    assert not relies_on("US:1:1", 1, "quoting X")      # a parenthetical that says nothing
    assert relies_on("US:1:1", 1, "holding that agencies get deference")


# Each guard below keeps a real citation from being called fabricated when the data cannot prove it.
# The name is invented, so without the guard each would be FABRICATED (bench/mutations.py checks this).
@pytest.mark.parametrize("cite, says", [
    ("6 U.S. 255 (1804)", "disagrees with how courts cite it"),               # volume's page map is suspect
    ("2 U.S. 408 (1793)", "Courts cite a case starting on page 408"),          # a start page missing from the data
    ("1 U.S. 471 (1789)", "holds several short orders"),                       # order pages
    ("1 F.3d 1585 (9th Cir. 1993)", "is the last page of United States v. Adams"),  # a shared last page
])
def test_guards_keep_unprovable_citations_unverifiable(cite, says):
    c = service.check_text(f"Zzyzx Holdings v. Quorvane Corp., {cite}.", suggest=False)["citations"][0]
    assert c["verdict"] == "UNVERIFIABLE", c["reason"]
    assert says in c["reason"]


@pytest.mark.parametrize("text, cite", [
    ("Chevron U.S.A. Inc. v. Natural Res. Def. Council, Inc., 467 U.S. 837 (1984).", "467 U.S. 837"),
    ("Nat'l Cable & Telecomms. Ass'n v. Brand X Internet Servs., 545 U.S. 967 (2005).", "545 U.S. 967"),
    ("Campbell v. Air Jamaica Ltd., 760 F.3d 1165 (11th Cir. 2014).", "760 F.3d 1165"),
])
def test_a_correct_citation_is_verified_under_its_short_or_abbreviated_name(text, cite):
    c = service.check_text(text, suggest=False)["citations"][0]
    assert c["verdict"] == "VERIFIED" and c["case"]["cite"] == cite
