
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
                    "attended_count": attended_count,
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

        course_ids = [course.id for course in courses]
        assessment_rows = db.execute(
            select(
                Assessment.course_id,
                Assessment.assessment_date,
                func.avg(
                    (AssessmentMark.marks / Assessment.max_marks) * 100
                ),
            )
            .join(
                AssessmentMark,
                AssessmentMark.assessment_id == Assessment.id,
            )
            .where(
                Assessment.course_id.in_(course_ids),
                Assessment.published.is_(True),
            )
            .group_by(Assessment.course_id, Assessment.assessment_date)
            .order_by(Assessment.assessment_date)
        ).all()

        timeline_dates = sorted(
            {assessment_date for _, assessment_date, _ in assessment_rows}
        )
        score_by_course_and_date = {
            (course_id, assessment_date): round(average, 1)
            for course_id, assessment_date, average in assessment_rows
        }
        palette = ["#0f9488", "#4f6bed", "#d97706", "#c2416c", "#64748b"]
        assessment_timeline = {
            "labels": [item.strftime("%b %d") for item in timeline_dates],
            "series": [
                {
                    "label": course.title,
                    "color": palette[index % len(palette)],
                    "values": [
                        score_by_course_and_date.get((course.id, date_value))
                        for date_value in timeline_dates
                    ],
                }
                for index, course in enumerate(courses)
                if any(
                    course.id == course_id
                    for course_id, _, _ in assessment_rows
                )
            ],
        }

        attendance_entry_count = sum(
            item["total_attendance"] for item in course_analytics
        )
        attended_entry_count = sum(
            item["attended_count"] for item in course_analytics
        )
        mark_count = sum(item["mark_count"] for item in course_analytics)
        weighted_score_total = sum(
            item["average_percentage"] * item["mark_count"]
            for item in course_analytics
            if item["average_percentage"] is not None
        )
        analytics_summary = {
            "courses": len(course_analytics),
            "course_enrollments": sum(
                item["student_count"] for item in course_analytics
            ),
            "attendance_percentage": (
                round(attended_entry_count / attendance_entry_count * 100, 1)
                if attendance_entry_count
                else None
            ),
            "average_percentage": (
                round(weighted_score_total / mark_count, 1)
                if mark_count
                else None
            ),
        }

        return render_template(
            "analytics_dashboard.html",
            course_analytics=course_analytics,
            assessment_timeline=assessment_timeline,
            analytics_summary=analytics_summary,
        )
