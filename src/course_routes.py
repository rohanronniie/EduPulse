
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

from src.auth_routes import role_required
from src.models import Course, StudentCourse
from src.portal_models import Assessment, AttendanceSession


courses_bp = Blueprint("courses", __name__, url_prefix="/courses")


@courses_bp.route("/")
@role_required("faculty")
def list_courses():
    """Display all registered courses."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        courses = session.scalars(
            select(Course).order_by(Course.course_code)
        ).all()

    return render_template("courses.html", courses=courses)


@courses_bp.route("/new", methods=["GET", "POST"])
@role_required("faculty")
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


@courses_bp.route("/<int:course_id>/edit", methods=["GET", "POST"])
@role_required("faculty")
def edit_course(course_id):
    """Update a course's identifying fields without changing linked records."""
    session_factory = current_app.config["SESSION_FACTORY"]
    with session_factory() as session:
        course = session.get(Course, course_id)
        if course is None:
            return "Course not found.", 404

        if request.method == "POST":
            course_code = request.form.get("course_code", "").strip()
            title = request.form.get("title", "").strip()
            if not course_code or not title:
                flash("Course code and title are required.", "error")
                return render_template("course_form.html", course=course), 400

            course.course_code = course_code
            course.title = title
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                flash(
                    "That course code is already in use. Choose another code.",
                    "error",
                )
                return render_template("course_form.html", course=course), 409

            flash("Course details updated.", "success")
            return redirect(url_for("courses.list_courses"))

        return render_template("course_form.html", course=course)


@courses_bp.route("/<int:course_id>/delete", methods=["POST"])
@role_required("faculty")
def delete_course(course_id):
    """Delete a course only when no student or academic history depends on it."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        course = session.get(Course, course_id)
        if course is None:
            return "Course not found.", 404

        has_enrollment = session.scalar(
            select(StudentCourse.id)
            .where(StudentCourse.course_id == course_id)
            .limit(1)
        )
        has_attendance = session.scalar(
            select(AttendanceSession.id)
            .where(AttendanceSession.course_id == course_id)
            .limit(1)
        )
        has_assessment = session.scalar(
            select(Assessment.id)
            .where(Assessment.course_id == course_id)
            .limit(1)
        )

        if any((has_enrollment, has_attendance, has_assessment)):
            flash(
                "This course cannot be deleted while it has enrollments, attendance "
                "sessions, or assessments. Remove only empty enrollments through the "
                "enrollment list; recorded academic data must be retained.",
                "error",
            )
            return redirect(url_for("courses.list_courses"))

        session.delete(course)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            flash(
                "The course could not be deleted because related records were added. "
                "Refresh the directory and review its enrollments and academic data.",
                "error",
            )
            return redirect(url_for("courses.list_courses"))

    flash("Course deleted.", "success")
    return redirect(url_for("courses.list_courses"))
