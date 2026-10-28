
from flask import Blueprint, abort, current_app, render_template
from sqlalchemy import select

from src.academic_engine import (
    generate_academic_report,
    recommend_interventions,
)
from src.academic_models import AcademicRecord
from src.auth_routes import role_required
from src.models import Course, Student, StudentCourse
from src.portal_models import (
    Assessment,
    AssessmentMark,
    AttendanceEntry,
    AttendanceSession,
    FacultyCourse,
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
    from src.auth_routes import get_current_user

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
    from src.auth_routes import get_current_user

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
                }
            )

        return render_template(
            "academic_support_report.html",
            course=course,
            reports=reports,
        )
