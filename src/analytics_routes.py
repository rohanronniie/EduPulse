
from flask import Blueprint, current_app, render_template
from sqlalchemy import func, select

from src.auth_routes import get_current_user, role_required
from src.models import Course, StudentCourse
from src.portal_models import (
    Assessment,
    AssessmentMark,
    AttendanceEntry,
    AttendanceSession,
    FacultyCourse,
)

analytics_bp = Blueprint(
    "analytics",
    __name__,
    url_prefix="/analytics",
)


@analytics_bp.route("/")
@role_required("faculty")
def dashboard():
    """Show course-level analytics for the logged-in faculty member."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        courses = db.scalars(
            select(Course)
            .join(FacultyCourse, FacultyCourse.course_id == Course.id)
            .where(FacultyCourse.faculty_id == user["id"])
            .order_by(Course.title)
        ).all()

        course_analytics = []

        for course in courses:
            student_count = db.scalar(
                select(func.count(func.distinct(StudentCourse.student_id)))
                .where(StudentCourse.course_id == course.id)
            ) or 0

            total_attendance = db.scalar(
                select(func.count(AttendanceEntry.id))
                .join(
                    AttendanceSession,
                    AttendanceEntry.session_id == AttendanceSession.id,
                )
                .where(AttendanceSession.course_id == course.id)
            ) or 0

            attended_count = db.scalar(
                select(func.count(AttendanceEntry.id))
                .join(
                    AttendanceSession,
                    AttendanceEntry.session_id == AttendanceSession.id,
                )
                .where(
                    AttendanceSession.course_id == course.id,
                    AttendanceEntry.status.in_(["present", "late"]),
                )
            ) or 0

            attendance_percentage = (
                round(attended_count / total_attendance * 100, 1)
                if total_attendance
                else None
            )

            published_assessment_count = db.scalar(
                select(func.count(Assessment.id)).where(
                    Assessment.course_id == course.id,
                    Assessment.published.is_(True),
                )
            ) or 0

            percentage = (
                AssessmentMark.marks / Assessment.max_marks
            ) * 100

            result = db.execute(
                select(
                    func.count(AssessmentMark.id),
                    func.avg(percentage),
                    func.min(percentage),
                    func.max(percentage),
                )
                .join(
                    Assessment,
                    AssessmentMark.assessment_id == Assessment.id,
                )
                .where(
                    Assessment.course_id == course.id,
                    Assessment.published.is_(True),
                )
            ).one()

            mark_count, average, lowest, highest = result

            course_analytics.append(
                {
                    "course": course,
                    "student_count": student_count,
                    "total_attendance": total_attendance,
                    "attendance_percentage": attendance_percentage,
                    "published_assessment_count": (
                        published_assessment_count
                    ),
                    "mark_count": mark_count or 0,
                    "average_percentage": (
                        round(average, 1) if average is not None else None
                    ),
                    "lowest_percentage": (
                        round(lowest, 1) if lowest is not None else None
                    ),
                    "highest_percentage": (
                        round(highest, 1) if highest is not None else None
                    ),
                }
            )

        return render_template(
            "analytics_dashboard.html",
            course_analytics=course_analytics,
        )
