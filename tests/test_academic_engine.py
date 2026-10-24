
import pytest

from src.academic_engine import evaluate_attendance
from src.academic_engine import evaluate_assignment_completion
from src.academic_engine import evaluate_assessment_trend
from src.academic_engine import generate_academic_report
from src.academic_engine import recommend_interventions
from src.academic_engine import compare_academic_scenarios

def test_low_attendance_triggers_support_flag():
    result = evaluate_attendance(60)

    assert result["status"] == "support_flag"
    assert result["evidence"]["attendance_percentage"] == 60
    assert result["evidence"]["threshold"] == 75.0


def test_attendance_at_threshold_does_not_trigger_flag():
    result = evaluate_attendance(75)

    assert result["status"] == "no_flag"


def test_high_attendance_does_not_trigger_flag():
    result = evaluate_attendance(90)

    assert result["status"] == "no_flag"


def test_missing_attendance_returns_insufficient_data():
    result = evaluate_attendance(None)

    assert result["status"] == "insufficient_data"


@pytest.mark.parametrize("attendance", [-5, 101])
def test_invalid_attendance_is_rejected(attendance):
    with pytest.raises(ValueError):
        evaluate_attendance(attendance)


def test_low_assignment_completion_triggers_flag():
    result = evaluate_assignment_completion(6, 10)

    assert result["status"] == "support_flag"
    assert result["evidence"]["completion_rate"] == 60.0


def test_completion_at_threshold_does_not_trigger_flag():
    result = evaluate_assignment_completion(8, 10)

    assert result["status"] == "no_flag"


def test_zero_assignments_returns_insufficient_data():
    result = evaluate_assignment_completion(0, 0)

    assert result["status"] == "insufficient_data"


def test_completed_assignments_cannot_exceed_total():
    with pytest.raises(ValueError):
        evaluate_assignment_completion(11, 10)


def test_negative_assignment_count_is_rejected():
    with pytest.raises(ValueError):
        evaluate_assignment_completion(-1, 10)


def test_boolean_assignment_count_is_rejected():
    with pytest.raises(TypeError):
        evaluate_assignment_completion(True, 10)


def test_declining_assessment_scores_trigger_flag():
    result = evaluate_assessment_trend([82, 71, 58])

    assert result["status"] == "support_flag"
    assert result["evidence"]["decline_percentage_points"] == 24


def test_improving_scores_do_not_trigger_flag():
    result = evaluate_assessment_trend([60, 70, 80])

    assert result["status"] == "no_flag"


def test_stable_scores_do_not_trigger_flag():
    result = evaluate_assessment_trend([70, 70, 70])

    assert result["status"] == "no_flag"


def test_single_assessment_returns_insufficient_data():
    result = evaluate_assessment_trend([80])

    assert result["status"] == "insufficient_data"


def test_invalid_assessment_score_is_rejected():
    with pytest.raises(ValueError):
        evaluate_assessment_trend([80, 105])


def test_boolean_assessment_score_is_rejected():
    with pytest.raises(TypeError):
        evaluate_assessment_trend([80, True])


def test_all_rules_trigger():
    report = generate_academic_report(60, [80, 50], 4, 10)

    assert report["overall_status"] == "support_recommended"
    assert len(report["triggered_rules"]) == 3


def test_only_attendance_triggers():
    report = generate_academic_report(60, [70, 75], 9, 10)

    assert report["overall_status"] == "support_recommended"
    assert report["triggered_rules"] == ["attendance"]


def test_no_rules_trigger():
    report = generate_academic_report(90, [70, 75], 9, 10)

    assert report["overall_status"] == "no_flag"
    assert report["triggered_rules"] == []


def test_insufficient_assessment_data():
    report = generate_academic_report(90, [80], 9, 10)

    assert report["overall_status"] == "incomplete_data"


def test_attendance_flag_survives_missing_assessment_data():
    report = generate_academic_report(60, [80], 9, 10)

    assert report["overall_status"] == "support_recommended"
    assert report["triggered_rules"] == ["attendance"]
    assert (
        report["findings"]["assessment_trend"]["status"]
        == "insufficient_data"
    )


def test_boolean_attendance_is_rejected():
    with pytest.raises(TypeError):
        evaluate_attendance(True)


@pytest.mark.parametrize("attendance", [float("nan"), float("inf")])
def test_non_finite_attendance_is_rejected(attendance):
    with pytest.raises(ValueError):
        evaluate_attendance(attendance)


def test_boolean_attendance_threshold_is_rejected():
    with pytest.raises(TypeError):
        evaluate_attendance(80, threshold=True)



def test_all_triggered_rules_produce_recommendations():
    report = generate_academic_report(60, [80, 50], 4, 10)

    result = recommend_interventions(report)

    assert len(result["recommendations"]) == 3
    assert result["data_gaps"] == []


def test_no_flags_produce_no_recommendations():
    report = generate_academic_report(90, [70, 75], 9, 10)

    result = recommend_interventions(report)

    assert result["recommendations"] == []
    assert result["data_gaps"] == []


def test_insufficient_data_is_reported_separately():
    report = generate_academic_report(90, [80], 9, 10)

    result = recommend_interventions(report)

    assert result["recommendations"] == []
    assert len(result["data_gaps"]) == 1
    assert result["data_gaps"][0]["rule"] == "assessment_trend"


def test_scenario_comparison_detects_improvements():
    current = {
        "attendance_percentage": 60,
        "assessment_scores": [80, 50],
        "completed_assignments": 4,
        "total_assignments": 10,
    }

    hypothetical = {
        "attendance_percentage": 80,
        "assessment_scores": [80, 75],
        "completed_assignments": 8,
        "total_assignments": 10,
    }

    result = compare_academic_scenarios(current, hypothetical)

    assert result["changes"]["attendance"]["status_changed"] is True
    assert result["changes"]["assessment_trend"]["status_changed"] is True
    assert result["changes"]["assignment_completion"]["status_changed"] is True
    assert result["hypothetical_overall_status"] == "no_flag"


def test_scenario_comparison_detects_unchanged_statuses():
    scenario = {
        "attendance_percentage": 90,
        "assessment_scores": [70, 75],
        "completed_assignments": 9,
        "total_assignments": 10,
    }

    result = compare_academic_scenarios(scenario, scenario)

    assert result["overall_status_changed"] is False

    for change in result["changes"].values():
        assert change["status_changed"] is False


def test_scenario_comparison_includes_evidence():
    current = {
        "attendance_percentage": 60,
        "assessment_scores": [80, 50],
        "completed_assignments": 4,
        "total_assignments": 10,
    }

    hypothetical = {
        "attendance_percentage": 80,
        "assessment_scores": [80, 75],
        "completed_assignments": 8,
        "total_assignments": 10,
    }

    result = compare_academic_scenarios(current, hypothetical)
    attendance = result["changes"]["attendance"]

    assert attendance["current_evidence"]["attendance_percentage"] == 60
    assert attendance["hypothetical_evidence"]["attendance_percentage"] == 80
    assert "current_reason" in attendance
    assert "hypothetical_reason" in attendance


def test_scenario_comparison_rejects_missing_fields():
    current = {
        "attendance_percentage": 60,
        "assessment_scores": [80, 50],
        "completed_assignments": 4,
        "total_assignments": 10,
    }

    incomplete_hypothetical = {
        "attendance_percentage": 80,
        "assessment_scores": [80, 75],
        "completed_assignments": 8,
    }

    with pytest.raises(ValueError, match="total_assignments"):
        compare_academic_scenarios(current, incomplete_hypothetical)
