"""The agent experiment's scoring logic: the arms differ only where they should, the sign test is
exact, and every FABRICATED verdict is audited against the store."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
import agent_experiment as e  # noqa: E402


def test_arms_differ_only_by_warning_and_tools():
    e.use("memory")
    task = e.load()["tasks"][0]
    a, b, c = (e.prompt(task, arm, None) for arm in "ABC")
    assert e.WARNING not in a and e.TOOLS not in a
    assert b == a + "\n\n" + e.WARNING
    assert c == b + "\n\n" + e.TOOLS


def test_packet_arms_share_the_packet():
    e.use("packet")
    task = e.load()["tasks"][0]
    packet = [{"name": "Chevron U.S.A. Inc. v. NRDC, 467 U.S. 837 (1984)", "cite": None, "note": "x"}]
    for arm in "ABC":
        assert "Chevron U.S.A. Inc. v. NRDC" in e.prompt(task, arm, packet)
    e.use("memory")


def test_sign_test_is_exact():
    assert e.sign_test(0, 0) == 1.0
    assert e.sign_test(5, 0) == 0.0625          # 2 * (1/2)^5
    assert abs(e.sign_test(10, 0) - 2 / 1024) < 1e-12
    assert e.sign_test(3, 3) == 1.0


def test_audit_finds_the_real_case_behind_a_wrong_citation():
    a = e.audit({"name": "Campbell v. Air Jamaica Ltd"})
    assert a["kind"] == "real case, wrong citation"
    assert "760 F.3d 1165" in a["real"]


def test_audit_reports_cases_that_do_not_exist():
    assert e.audit({"name": "Varghese v. China Southern Airlines"})["real"] is None


def test_judge_cannot_see_the_arm():
    assert "Redline" not in e.scrub("Redline confirmed it. I ran check_citations and search_cases.")
