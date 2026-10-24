
import math


def evaluate_attendance(attendance_percentage, threshold=75.0):
    """Evaluate attendance and return an explainable support indicator."""

    if attendance_percentage is None:
        return {
            "status": "insufficient_data",
            "reason": "Attendance data is unavailable.",
        }

    if isinstance(attendance_percentage, bool) or not isinstance(
        attendance_percentage, (int, float)
    ):
        raise TypeError("Attendance must be a number.")

    if not math.isfinite(attendance_percentage):
        raise ValueError("Attendance must be a finite number.")

    if not 0 <= attendance_percentage <= 100:
        raise ValueError("Attendance must be between 0 and 100.")

    if isinstance(threshold, bool) or not isinstance(
        threshold, (int, float)
    ):
        raise TypeError("Threshold must be numeric.")

    if not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError("Threshold must be finite and between 0 and 100.")

    evidence = {
        "attendance_percentage": attendance_percentage,
        "threshold": threshold,
    }

    if attendance_percentage < threshold:
        return {
            "status": "support_flag",
            "reason": (
                f"Attendance is {attendance_percentage:.1f}%, "
                f"below the configured threshold of {threshold:.1f}%."
            ),
            "evidence": evidence,
        }

    return {
        "status": "no_flag",
        "reason": "Attendance meets the configured threshold.",
        "evidence": evidence,
    }


def evaluate_assignment_completion(
    completed_assignments,
    total_assignments,
    threshold=80.0,
):
    """Evaluate assignment completion and explain any support flag."""

    if isinstance(completed_assignments, bool) or not isinstance(
        completed_assignments, int
    ):
        raise TypeError("Completed assignments must be an integer.")

    if isinstance(total_assignments, bool) or not isinstance(
        total_assignments, int
    ):
        raise TypeError("Total assignments must be an integer.")

    if completed_assignments < 0 or total_assignments < 0:
        raise ValueError("Assignment counts cannot be negative.")

    if completed_assignments > total_assignments:
        raise ValueError(
            "Completed assignments cannot exceed total assignments."
        )

    if isinstance(threshold, bool) or not isinstance(
        threshold, (int, float)
    ):
        raise TypeError("Threshold must be numeric.")

    if not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError("Threshold must be finite and between 0 and 100.")

    if total_assignments == 0:
        return {
            "status": "insufficient_data",
            "reason": "No assignments are available for evaluation.",
        }

    completion_rate = completed_assignments / total_assignments * 100

    evidence = {
        "completed_assignments": completed_assignments,
        "total_assignments": total_assignments,
        "completion_rate": round(completion_rate, 2),
        "threshold": threshold,
    }

    if completion_rate < threshold:
        return {
            "status": "support_flag",
            "reason": (
                f"Assignment completion is {completion_rate:.1f}%, "
                f"below the configured threshold of {threshold:.1f}%."
            ),
            "evidence": evidence,
        }

    return {
        "status": "no_flag",
        "reason": "Assignment completion meets the configured threshold.",
        "evidence": evidence,
    }


def evaluate_assessment_trend(scores, decline_threshold=15.0):
    """Identify a decline between the first and latest assessment."""

    if not isinstance(scores, (list, tuple)):
        raise TypeError("Scores must be a list or tuple.")

    if len(scores) < 2:
        return {
            "status": "insufficient_data",
            "reason": "At least two assessments are required.",
        }

    if isinstance(decline_threshold, bool) or not isinstance(
        decline_threshold, (int, float)
    ):
        raise TypeError("Decline threshold must be numeric.")

    if not math.isfinite(decline_threshold) or not (
        0 <= decline_threshold <= 100
    ):
        raise ValueError(
            "Decline threshold must be finite and between 0 and 100."
        )

    for score in scores:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise TypeError("Every assessment score must be numeric.")

        if not math.isfinite(score):
            raise ValueError("Assessment scores must be finite numbers.")

        if not 0 <= score <= 100:
            raise ValueError("Assessment scores must be between 0 and 100.")

    first_score = scores[0]
    latest_score = scores[-1]
    decline = first_score - latest_score

    evidence = {
        "first_score": first_score,
        "latest_score": latest_score,
        "decline_percentage_points": round(decline, 2),
        "decline_threshold": decline_threshold,
    }

    if decline >= decline_threshold and decline > 0:
        return {
            "status": "support_flag",
            "reason": (
                f"Assessment performance declined by {decline:.1f} "
                f"percentage points, from {first_score}% "
                f"to {latest_score}%."
            ),
            "evidence": evidence,
        }

    return {
        "status": "no_flag",
        "reason": "The assessment trend does not meet the decline rule.",
        "evidence": evidence,
    }


def generate_academic_report(
    attendance_percentage,
    assessment_scores,
    completed_assignments,
    total_assignments,
):
    """Combine individual academic evaluations into one report."""

    attendance = evaluate_attendance(attendance_percentage)

    assessment = evaluate_assessment_trend(assessment_scores)

    assignments = evaluate_assignment_completion(
        completed_assignments,
        total_assignments,
    )

    findings = {
        "attendance": attendance,
        "assessment_trend": assessment,
        "assignment_completion": assignments,
    }

    triggered_rules = [
        name
        for name, result in findings.items()
        if result["status"] == "support_flag"
    ]

    if triggered_rules:
        overall_status = "support_recommended"
    elif any(
        result["status"] == "insufficient_data"
        for result in findings.values()
    ):
        overall_status = "incomplete_data"
    else:
        overall_status = "no_flag"

    return {
        "overall_status": overall_status,
        "findings": findings,
        "triggered_rules": triggered_rules,
    }




def recommend_interventions(report):
    """Suggest follow-up actions and identify missing academic data."""

    recommendations = []
    data_gaps = []

    findings = report["findings"]

    for rule_name, finding in findings.items():
        if finding["status"] == "insufficient_data":
            data_gaps.append({
                "rule": rule_name,
                "message": finding["reason"],
            })

    if findings["attendance"]["status"] == "support_flag":
        recommendations.append({
            "rule": "attendance",
            "action": (
                "Review recent attendance with the student and ask "
                "whether any barriers are affecting participation."
            ),
        })

    if findings["assessment_trend"]["status"] == "support_flag":
        recommendations.append({
            "rule": "assessment_trend",
            "action": (
                "Review recent assessments with the student to identify "
                "topics where additional academic support may help."
            ),
        })

    if findings["assignment_completion"]["status"] == "support_flag":
        recommendations.append({
            "rule": "assignment_completion",
            "action": (
                "Discuss assignment workload, deadlines, and any support "
                "needed to complete outstanding work."
            ),
        })

    return {
        "recommendations": recommendations,
        "data_gaps": data_gaps,
    }


def _validate_scenario(scenario, scenario_name):
    """Validate the structure of an academic scenario."""

    required_fields = {
        "attendance_percentage",
        "assessment_scores",
        "completed_assignments",
        "total_assignments",
    }

    if not isinstance(scenario, dict):
        raise ValueError(
            f"{scenario_name} must be a dictionary."
        )

    missing_fields = required_fields - scenario.keys()

    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(
            f"{scenario_name} is missing required fields: {missing}"
        )

def compare_academic_scenarios(current_scenario, hypothetical_scenario):
    """Compare current and hypothetical academic scenarios."""

    _validate_scenario(current_scenario, "Current scenario")
    _validate_scenario(hypothetical_scenario, "Hypothetical scenario")

    current_report = generate_academic_report(
        attendance_percentage=current_scenario["attendance_percentage"],
        assessment_scores=current_scenario["assessment_scores"],
        completed_assignments=current_scenario["completed_assignments"],
        total_assignments=current_scenario["total_assignments"],
    )

    hypothetical_report = generate_academic_report(
        attendance_percentage=hypothetical_scenario["attendance_percentage"],
        assessment_scores=hypothetical_scenario["assessment_scores"],
        completed_assignments=hypothetical_scenario["completed_assignments"],
        total_assignments=hypothetical_scenario["total_assignments"],
    )

    
    changes = {}

    for rule_name, current_finding in current_report["findings"].items():
        hypothetical_finding = hypothetical_report["findings"][rule_name]

        changes[rule_name] = {
            "current_status": current_finding["status"],
            "hypothetical_status": hypothetical_finding["status"],
            "status_changed": (
                current_finding["status"]
                != hypothetical_finding["status"]
            ),
            "current_reason": current_finding["reason"],
            "hypothetical_reason": hypothetical_finding["reason"],
            "current_evidence": current_finding["evidence"],
            "hypothetical_evidence": hypothetical_finding["evidence"],
        }


    return {
        "current_overall_status": current_report["overall_status"],
        "hypothetical_overall_status": hypothetical_report["overall_status"],
        "overall_status_changed": (
            current_report["overall_status"]
            != hypothetical_report["overall_status"]
        ),
        "changes": changes,
    }