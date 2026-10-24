
from flask import Flask

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

    from flask import render_template

    @app.route("/")
    def home():
        """Display the EduPulse homepage."""
        return render_template("index.html")

    @app.route("/health")
    def health_check():
        """Return a simple application health response."""
        return {"status": "healthy", "application": "EduPulse"}

    return app
