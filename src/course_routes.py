
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models import Course


courses_bp = Blueprint("courses", __name__, url_prefix="/courses")


@courses_bp.route("/")
def list_courses():
    """Display all registered courses."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        courses = session.scalars(
            select(Course).order_by(Course.course_code)
        ).all()

    return render_template("courses.html", courses=courses)


@courses_bp.route("/new", methods=["GET", "POST"])
def create_course():
    """Display the course form and create a course."""
    if request.method == "POST":
        course_code = request.form.get("course_code", "").strip()
        title = request.form.get("title", "").strip()

        if not course_code or not title:
            flash("Course code and title are required.", "error")
            return render_template("course_form.html")

        session_factory = current_app.config["SESSION_FACTORY"]

        with session_factory() as session:
            course = Course(
                course_code=course_code,
                title=title,
            )
            session.add(course)

            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                flash(
                    "That course code already exists. Please use a unique code.",
                    "error",
                )
                return render_template("course_form.html"), 409

        flash("Course created successfully.", "success")
        return redirect(url_for("courses.list_courses"))

    return render_template("course_form.html")
