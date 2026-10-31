import os

from flask import Flask, render_template
from sqlalchemy import case, func, select, text
from flask_wtf.csrf import CSRFProtect

from src.course_routes import courses_bp
from src.database import SessionLocal, initialize_database
from src.student_routes import students_bp
from src.enrollment_routes import enrollment_bp
from src.academic_routes import academic_bp
from src.models import Student, Course, StudentCourse
from src.academic_models import AcademicRecord
from src.portal_models import (
    User,
    FacultyCourse,
    AttendanceSession,
    AttendanceEntry,
    Assessment,
    AssessmentMark,
    SupportFollowUp,
)
from src.auth_routes import auth_bp, login_required, get_current_user
from src.attendance_routes import attendance_bp
from src.assessment_routes import assessment_bp
from src.analytics_routes import analytics_bp
from src.academic_support_routes import academic_support_bp

def create_app(test_config=None):
    """Create and configure the EduPulse Flask application."""
    app = Flask(__name__)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("EDUPULSE_SECRET_KEY"),
        INITIALIZE_DATABASE=True,
        SESSION_FACTORY=SessionLocal,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(
            os.environ.get("EDUPULSE_ENV", "development").lower()
            == "production"
        ),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )

    if test_config is not None:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        if app.config.get("TESTING"):
            app.config["SECRET_KEY"] = "test-only-secret-key"
        else:
            raise RuntimeError(
                "EDUPULSE_SECRET_KEY must be set before starting EduPulse."
            )

    csrf = CSRFProtect()
    csrf.init_app(app)

    if app.config["INITIALIZE_DATABASE"]:
        initialize_database()

    @app.after_request
    def add_security_headers(response):
        """Set baseline browser security headers."""
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy",
            "strict-origin-when-cross-origin",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    app.register_blueprint(students_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(enrollment_bp)
    app.register_blueprint(academic_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(assessment_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(academic_support_bp)

    @app.context_processor
    def inject_current_user():
        return {"current_user": get_current_user()}

    @app.route("/")
    @login_required
    def home():
        """Show the dashboard appropriate to the logged-in user's role."""
        user = get_current_user()
        session_factory = app.config["SESSION_FACTORY"]

        with session_factory() as db:
            if user["role"] == "student":
                student_id = user["student_id"]

                if student_id is None:
                    return (
                        "This student account is not linked to a student record.",
                        403,
                    )

                student = db.get(Student, student_id)
                if student is None:
                    return "Student record not found.", 404

                courses = db.scalars(
                    select(Course)
                    .join(StudentCourse, StudentCourse.course_id == Course.id)
                    .where(StudentCourse.student_id == student_id)
                    .order_by(Course.title)
                ).all()
                course_ids = [course.id for course in courses]

                attendance_rows = db.execute(
                    select(
                        AttendanceSession.course_id,
                        func.count(AttendanceEntry.id),
                        func.sum(
                            case(
                                (
                                    AttendanceEntry.status.in_(
                                        ["present", "late"]
                                    ),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                    )
                    .join(
                        AttendanceSession,
                        AttendanceEntry.session_id == AttendanceSession.id,
                    )
                    .where(
                        AttendanceEntry.student_id == student_id,
                        AttendanceSession.course_id.in_(course_ids),
                    )
                    .group_by(AttendanceSession.course_id)
                ).all()
                attendance_by_course = {
                    course_id: {
                        "total": total or 0,
                        "attended": attended or 0,
                    }
                    for course_id, total, attended in attendance_rows
                }

                total_sessions = db.scalar(
                    select(func.count(AttendanceEntry.id))
                    .join(
                        AttendanceSession,
                        AttendanceEntry.session_id == AttendanceSession.id,
                    )
                    .where(AttendanceEntry.student_id == student_id)
                ) or 0

                attended_sessions = db.scalar(
                    select(func.count(AttendanceEntry.id))
                    .join(
                        AttendanceSession,
                        AttendanceEntry.session_id == AttendanceSession.id,
                    )
                    .where(
                        AttendanceEntry.student_id == student_id,
                        AttendanceEntry.status.in_(["present", "late"]),
                    )
                ) or 0

                attendance_percentage = (
                    round(attended_sessions / total_sessions * 100, 1)
                    if total_sessions
                    else None
                )

                published_marks = db.execute(
                    select(
                        Assessment.title,
                        Assessment.max_marks,
                        AssessmentMark.marks,
                        Assessment.course_id,
                        Course.title.label("course_title"),
                        Assessment.assessment_date,
                    )
                    .join(
                        AssessmentMark,
                        AssessmentMark.assessment_id == Assessment.id,
                    )
                    .join(Course, Course.id == Assessment.course_id)
                    .where(
                        AssessmentMark.student_id == student_id,
                        Assessment.published.is_(True),
                    )
                    .order_by(Assessment.assessment_date.desc())
                ).all()

                marks_by_course = {}
                for mark in published_marks:
                    score_percentage = round(
                        mark.marks / mark.max_marks * 100,
                        1,
                    )
                    marks_by_course.setdefault(mark.course_id, []).append(
                        {
                            "title": mark.title,
                            "course_title": mark.course_title,
                            "marks": mark.marks,
                            "max_marks": mark.max_marks,
                            "percentage": score_percentage,
                        }
                    )

                student_course_analytics = []
                for course in courses:
                    attendance = attendance_by_course.get(
                        course.id,
                        {"total": 0, "attended": 0},
                    )
                    total = attendance["total"]
                    student_course_analytics.append(
                        {
                            "course": course,
                            "attendance_percentage": (
                                round(attendance["attended"] / total * 100, 1)
                                if total
                                else None
                            ),
                            "attendance_total": total,
                            "assessment_marks": marks_by_course.get(
                                course.id,
                                [],
                            ),
                        }
                    )

                return render_template(
                    "student_dashboard.html",
                    student=student,
                    courses=courses,
                    total_sessions=total_sessions,
                    attended_sessions=attended_sessions,
                    attendance_percentage=attendance_percentage,
                    published_marks=published_marks,
                    student_course_analytics=student_course_analytics,
                )

            if user["role"] == "faculty":
                assigned_courses = db.scalars(
                    select(Course)
                    .join(
                        FacultyCourse,
                        FacultyCourse.course_id == Course.id,
                    )
                    .where(FacultyCourse.faculty_id == user["id"])
                    .order_by(Course.title)
                ).all()

                course_ids = [course.id for course in assigned_courses]

                if course_ids:
                    enrolled_student_count = db.scalar(
                        select(func.count(func.distinct(StudentCourse.student_id)))
                        .where(StudentCourse.course_id.in_(course_ids))
                    ) or 0

                    session_count = db.scalar(
                        select(func.count(AttendanceSession.id)).where(
                            AttendanceSession.faculty_id == user["id"],
                            AttendanceSession.course_id.in_(course_ids),
                        )
                    ) or 0

                    assessment_count = db.scalar(
                        select(func.count(Assessment.id)).where(
                            Assessment.faculty_id == user["id"],
                            Assessment.course_id.in_(course_ids),
                        )
                    ) or 0

                    open_follow_up_count = db.scalar(
                        select(func.count(SupportFollowUp.id))
                        .join(
                            StudentCourse,
                            StudentCourse.id
                            == SupportFollowUp.student_course_id,
                        )
                        .where(
                            StudentCourse.course_id.in_(course_ids),
                            SupportFollowUp.status != "completed",
                        )
                    ) or 0

                    attendance_rows = db.execute(
                        select(
                            AttendanceSession.course_id,
                            func.count(AttendanceEntry.id),
                            func.sum(
                                case(
                                    (
                                        AttendanceEntry.status.in_(
                                            ["present", "late"]
                                        ),
                                        1,
                                    ),
                                    else_=0,
                                )
                            ),
                        )
                        .join(
                            AttendanceSession,
                            AttendanceEntry.session_id
                            == AttendanceSession.id,
                        )
                        .where(AttendanceSession.course_id.in_(course_ids))
                        .group_by(AttendanceSession.course_id)
                    ).all()
                    attendance_by_course = {
                        course_id: (total or 0, attended or 0)
                        for course_id, total, attended in attendance_rows
                    }

                    average_rows = db.execute(
                        select(
                            Assessment.course_id,
                            func.avg(
                                (AssessmentMark.marks / Assessment.max_marks)
                                * 100
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
                        .group_by(Assessment.course_id)
                    ).all()
                    average_by_course = {
                        course_id: round(average, 1)
                        for course_id, average in average_rows
                        if average is not None
                    }
                    faculty_course_analytics = []
                    for course in assigned_courses:
                        total, attended = attendance_by_course.get(
                            course.id,
                            (0, 0),
                        )
                        faculty_course_analytics.append(
                            {
                                "course": course,
                                "attendance_percentage": (
                                    round(attended / total * 100, 1)
                                    if total
                                    else None
                                ),
                                "average_percentage": average_by_course.get(
                                    course.id
                                ),
                            }
                        )
                else:
                    enrolled_student_count = 0
                    session_count = 0
                    assessment_count = 0
                    open_follow_up_count = 0
                    faculty_course_analytics = []

                return render_template(
                    "faculty_dashboard.html",
                    username=user["username"],
                    courses=assigned_courses,
                    enrolled_student_count=enrolled_student_count,
                    session_count=session_count,
                    assessment_count=assessment_count,
                    open_follow_up_count=open_follow_up_count,
                    course_analytics=faculty_course_analytics,
                )

            return "Unsupported account role.", 403

    @app.route("/student/courses/<int:course_id>")
    @login_required
    def student_course_detail(course_id):
        """Show a student's dated attendance and published marks for a subject."""
        user = get_current_user()
        if user["role"] != "student" or user["student_id"] is None:
            return "Student course details are available to student accounts only.", 403

        session_factory = app.config["SESSION_FACTORY"]
        with session_factory() as db:
            course = db.scalar(
                select(Course)
                .join(StudentCourse, StudentCourse.course_id == Course.id)
                .where(
                    Course.id == course_id,
                    StudentCourse.student_id == user["student_id"],
                )
            )
            if course is None:
                return "Subject not found.", 404

            attendance_records = db.execute(
                select(
                    AttendanceSession.session_date,
                    AttendanceSession.topic,
                    AttendanceEntry.status,
                )
                .join(
                    AttendanceEntry,
                    AttendanceEntry.session_id == AttendanceSession.id,
                )
                .where(
                    AttendanceSession.course_id == course_id,
                    AttendanceEntry.student_id == user["student_id"],
                )
                .order_by(
                    AttendanceSession.session_date.desc(),
                    AttendanceSession.id.desc(),
                )
            ).all()

            assessment_records = db.execute(
                select(
                    Assessment.title,
                    Assessment.assessment_date,
                    Assessment.max_marks,
                    AssessmentMark.marks,
                )
                .join(
                    AssessmentMark,
                    AssessmentMark.assessment_id == Assessment.id,
                )
                .where(
                    Assessment.course_id == course_id,
                    AssessmentMark.student_id == user["student_id"],
                    Assessment.published.is_(True),
                )
                .order_by(Assessment.assessment_date.desc(), Assessment.id.desc())
            ).all()

            attended_count = sum(
                record.status in {"present", "late"}
                for record in attendance_records
            )
            attendance_percentage = (
                round(attended_count / len(attendance_records) * 100, 1)
                if attendance_records
                else None
            )
            average_assessment = (
                round(
                    sum(
                        record.marks / record.max_marks * 100
                        for record in assessment_records
                    )
                    / len(assessment_records),
                    1,
                )
                if assessment_records
                else None
            )

            return render_template(
                "student_course_detail.html",
                student_name=db.get(Student, user["student_id"]).full_name,
                course=course,
                attendance_records=attendance_records,
                assessment_records=assessment_records,
                attendance_percentage=attendance_percentage,
                average_assessment=average_assessment,
                attended_count=attended_count,
            )

    @app.route("/health")
    def health_check():
        """Check application and database readiness for deployment probes."""
        session_factory = app.config["SESSION_FACTORY"]
        try:
            with session_factory() as db:
                db.execute(text("SELECT 1"))
        except Exception:
            app.logger.exception("Health check database connection failed")
            return {
                "status": "unavailable",
                "application": "EduPulse",
                "database": "unavailable",
            }, 503

        return {
            "status": "healthy",
            "application": "EduPulse",
            "database": "available",
        }

    return app
