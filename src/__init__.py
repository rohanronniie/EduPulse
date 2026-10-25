
from flask import Flask, render_template
from sqlalchemy import func, select

from src.course_routes import courses_bp
from src.database import SessionLocal, initialize_database
from src.student_routes import students_bp
from src.enrollment_routes import enrollment_bp
from src.academic_routes import academic_bp
from src.models import Student, Course, StudentCourse
from src.academic_models import AcademicRecord


def create_app(test_config=None):
    """Create and configure the EduPulse Flask application."""
    app = Flask(__name__)

    app.config.from_mapping(
        SECRET_KEY="dev-only-change-me",
        INITIALIZE_DATABASE=True,
        SESSION_FACTORY=SessionLocal,
    )

    if test_config is not None:
        app.config.update(test_config)

    if app.config["INITIALIZE_DATABASE"]:
        initialize_database()

    app.register_blueprint(students_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(enrollment_bp)
    app.register_blueprint(academic_bp)

    @app.route("/")
    def home():
        """Display the dashboard with live database statistics."""
        session_factory = app.config["SESSION_FACTORY"]

        with session_factory() as session:
            student_count = session.scalar(
                select(func.count()).select_from(Student)
            )
            course_count = session.scalar(
                select(func.count()).select_from(Course)
            )
            enrollment_count = session.scalar(
                select(func.count()).select_from(StudentCourse)
            )
            academic_record_count = session.scalar(
                select(func.count()).select_from(AcademicRecord)
            )

        return render_template(
            "index.html",
            student_count=student_count or 0,
            course_count=course_count or 0,
            enrollment_count=enrollment_count or 0,
            academic_record_count=academic_record_count or 0,
        )

    @app.route("/health")
    def health_check():
        """Return a simple application health response."""
        return {"status": "healthy", "application": "EduPulse"}

    return app
