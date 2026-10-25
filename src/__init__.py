
from flask import Flask, render_template

from src.course_routes import courses_bp
from src.database import SessionLocal, initialize_database
from src.student_routes import students_bp


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

    @app.route("/")
    def home():
        """Display the EduPulse homepage."""
        return render_template("index.html")

    @app.route("/health")
    def health_check():
        """Return a simple application health response."""
        return {"status": "healthy", "application": "EduPulse"}

    return app
