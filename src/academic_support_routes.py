
from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import select

from src.academic_engine import (
    generate_academic_report,
    recommend_interventions,
)
from src.academic_models import AcademicRecord
from src.auth_routes import get_current_user, role_required
from src.models import Course, Student, StudentCourse
from src.portal_models import (
    Assessment,
    AssessmentMark,
    AttendanceEntry,
    AttendanceSession,
    FacultyCourse,
    SupportFollowUp,
)


academic_support_bp = Blueprint(
    "academic_support",
    __name__,
    url_prefix="/academic-support",
)


@academic_support_bp.route("/")
@role_required("faculty")
def index():
    """List courses assigned to the current faculty member."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        courses = db.scalars(
            select(Course)
            .join(FacultyCourse, FacultyCourse.course_id == Course.id)
            .where(FacultyCourse.faculty_id == user["id"])
            .order_by(Course.title)
        ).all()

        return render_template(
            "academic_support_courses.html",
            courses=courses,
        )


@academic_support_bp.route("/<int:course_id>")
@role_required("faculty")
def course_report(course_id):
    """Generate explainable support reports for an assigned course."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        assigned = db.scalar(
            select(FacultyCourse.id).where(
                FacultyCourse.faculty_id == user["id"],
                FacultyCourse.course_id == course_id,
            )
        )

        if assigned is None:
            abort(404)

        course = db.get(Course, course_id)
        if course is None:
            abort(404)

        enrollments = db.scalars(
            select(StudentCourse)
            .where(StudentCourse.course_id == course_id)
            .order_by(StudentCourse.id)
        ).all()

        follow_ups_by_enrollment = {}
        follow_ups = db.scalars(
            select(SupportFollowUp)
            .join(
                StudentCourse,
                StudentCourse.id == SupportFollowUp.student_course_id,
            )
            .where(StudentCourse.course_id == course_id)
            .order_by(SupportFollowUp.created_at.desc())
        ).all()
        for follow_up in follow_ups:
            follow_ups_by_enrollment.setdefault(
                follow_up.student_course_id, []
            ).append(follow_up)

        reports = []

        for enrollment in enrollments:
            student = db.get(Student, enrollment.student_id)
            if student is None:
                continue

            # Calculate attendance only from this student's records
            # for this specific course.
            attendance_rows = db.execute(
                select(AttendanceEntry.status)
                .join(
                    AttendanceSession,
                    AttendanceSession.id == AttendanceEntry.session_id,
                )
                .where(
                    AttendanceSession.course_id == course_id,
                    AttendanceEntry.student_id == student.id,
                )
            ).all()

            total_sessions = len(attendance_rows)
            attended_sessions = sum(
                status in ("present", "late")
                for (status,) in attendance_rows
            )

            attendance_percentage = (
                attended_sessions / total_sessions * 100
                if total_sessions
                else None
            )

            # Use published marks only, in chronological order.
            published_marks = db.execute(
                select(
                    AssessmentMark.marks,
                    Assessment.max_marks,
                )
                .join(
                    Assessment,
                    Assessment.id == AssessmentMark.assessment_id,
                )
                .where(
                    Assessment.course_id == course_id,
                    Assessment.published.is_(True),
                    AssessmentMark.student_id == student.id,
                )
                .order_by(Assessment.assessment_date, Assessment.id)
            ).all()

            assessment_scores = [
                round((marks / max_marks) * 100, 2)
                for marks, max_marks in published_marks
            ]

            # Assignment completion comes from the existing academic record.
            academic_record = db.scalar(
                select(AcademicRecord).where(
                    AcademicRecord.student_course_id == enrollment.id
                )
            )

            if academic_record is None:
                completed_assignments = 0
                total_assignments = 0
            else:
                completed_assignments = (
                    academic_record.completed_assignments
                )
                total_assignments = academic_record.total_assignments

            report = generate_academic_report(
                attendance_percentage=attendance_percentage,
                assessment_scores=assessment_scores,
                completed_assignments=completed_assignments,
                total_assignments=total_assignments,
            )

            interventions = recommend_interventions(report)

            reports.append(
                {
                    "student": student,
                    "report": report,
                    "interventions": interventions,
                    "attendance_percentage": attendance_percentage,
                    "assessment_count": len(assessment_scores),
                    "assignment_data_available": academic_record is not None,
                    "enrollment_id": enrollment.id,
                    "follow_ups": follow_ups_by_enrollment.get(
                        enrollment.id, []
                    ),
                }
            )

        summary = {
            "students": len(reports),
            "support_recommended": sum(
                item["report"]["overall_status"] == "support_recommended"
                for item in reports
            ),
            "open_follow_ups": sum(
                follow_up.status != "completed"
                for item in reports
                for follow_up in item["follow_ups"]
            ),
        }

        return render_template(
            "academic_support_report.html",
            course=course,
            reports=reports,
            summary=summary,
        )


@academic_support_bp.route("/<int:course_id>/follow-ups", methods=["POST"])
@role_required("faculty")
def create_follow_up(course_id):
    """Record a support action for a student in an assigned course."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    enrollment_id = request.form.get("enrollment_id", type=int)
    finding_rule = request.form.get("finding_rule", "").strip()
    action_text = request.form.get("action_text", "").strip()
    notes = request.form.get("notes", "").strip()
    due_date_value = request.form.get("due_date", "").strip()

    if finding_rule not in {
        "attendance",
        "assessment_trend",
        "assignment_completion",
        "general",
    }:
        abort(400)

    if not action_text or len(action_text) > 300 or len(notes) > 2000:
        flash("Enter a support action and keep notes under 2,000 characters.", "error")
        return redirect(
            url_for("academic_support.course_report", course_id=course_id)
        )

    due_date = None
    if due_date_value:
        try:
            due_date = date.fromisoformat(due_date_value)
        except ValueError:
            flash("Enter a valid follow-up date.", "error")
            return redirect(
                url_for("academic_support.course_report", course_id=course_id)
            )

    with session_factory() as db:
        enrollment = db.scalar(
            select(StudentCourse)
            .join(
                FacultyCourse,
                FacultyCourse.course_id == StudentCourse.course_id,
            )
            .where(
                StudentCourse.id == enrollment_id,
                StudentCourse.course_id == course_id,
                FacultyCourse.faculty_id == user["id"],
            )
        )
        if enrollment is None:
            abort(404)

        db.add(
            SupportFollowUp(
                student_course_id=enrollment.id,
                faculty_id=user["id"],
                finding_rule=finding_rule,
                action_text=action_text,
                notes=notes,
                due_date=due_date,
            )
        )
        db.commit()

    flash("Support follow-up recorded.", "success")
    return redirect(
        url_for("academic_support.course_report", course_id=course_id)
    )


@academic_support_bp.route(
    "/follow-ups/<int:follow_up_id>/status",
    methods=["POST"],
)
@role_required("faculty")
def update_follow_up_status(follow_up_id):
    """Update the completion state of an assigned course follow-up."""
    user = get_current_user()
    status = request.form.get("status", "").strip()
    if status not in {"open", "in_progress", "completed"}:
        abort(400)

    session_factory = current_app.config["SESSION_FACTORY"]
    with session_factory() as db:
        follow_up = db.scalar(
            select(SupportFollowUp)
            .join(
                StudentCourse,
                StudentCourse.id == SupportFollowUp.student_course_id,
            )
            .join(
                FacultyCourse,
                FacultyCourse.course_id == StudentCourse.course_id,
            )
            .where(
                SupportFollowUp.id == follow_up_id,
                FacultyCourse.faculty_id == user["id"],
            )
        )
        if follow_up is None:
            abort(404)

        follow_up.status = status
        db.commit()

        enrollment = db.get(StudentCourse, follow_up.student_course_id)
        course_id = enrollment.course_id

    flash("Follow-up status updated.", "success")
    return redirect(
        url_for("academic_support.course_report", course_id=course_id)
    )
