import os

from flask import Flask, render_template
from sqlalchemy import func, select
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

                return render_template(
                    "student_dashboard.html",
                    student=student,
                    courses=courses,
                    total_sessions=total_sessions,
                    attended_sessions=attended_sessions,
                    attendance_percentage=attendance_percentage,
                    published_marks=published_marks,
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
                else:
                    enrolled_student_count = 0
                    session_count = 0
                    assessment_count = 0

                return render_template(
                    "faculty_dashboard.html",
                    username=user["username"],
                    courses=assigned_courses,
                    enrolled_student_count=enrolled_student_count,
                    session_count=session_count,
                    assessment_count=assessment_count,
                )

            return "Unsupported account role.", 403

    @app.route("/health")
    def health_check():
        """Return a simple application health response."""
        return {"status": "healthy", "application": "EduPulse"}

    return app
