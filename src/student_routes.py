
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
from src.models import Student, StudentCourse
from src.portal_models import (
    AssessmentMark,
    AttendanceEntry,
    User,
)


students_bp = Blueprint("students", __name__, url_prefix="/students")


@students_bp.route("/")
@role_required("faculty")
def list_students():
    """Display all registered students."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        students = session.scalars(
            select(Student).order_by(Student.full_name)
        ).all()

    return render_template("students.html", students=students)


@students_bp.route("/new", methods=["GET", "POST"])
@role_required("faculty")
def create_student():
    """Display the registration form and create a student."""
    if request.method == "POST":
        student_code = request.form.get("student_code", "").strip()
        full_name = request.form.get("full_name", "").strip()

        if not student_code or not full_name:
            flash("Student code and full name are required.", "error")
            return render_template("student_form.html")

        session_factory = current_app.config["SESSION_FACTORY"]

        with session_factory() as session:
            student = Student(
                student_code=student_code,
                full_name=full_name,
            )
            session.add(student)

            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                flash(
                    "That student code already exists. Please use a unique code.",
                    "error",
                )
                return render_template("student_form.html"), 409

        flash("Student registered successfully.", "success")
        return redirect(url_for("students.list_students"))

    return render_template("student_form.html")


@students_bp.route("/<int:student_id>/edit", methods=["GET", "POST"])
@role_required("faculty")
def edit_student(student_id):
    """Update a student's directory identity without changing linked records."""
    session_factory = current_app.config["SESSION_FACTORY"]
    with session_factory() as session:
        student = session.get(Student, student_id)
        if student is None:
            return "Student not found.", 404

        if request.method == "POST":
            student_code = request.form.get("student_code", "").strip()
            full_name = request.form.get("full_name", "").strip()
            if not student_code or not full_name:
                flash("Student code and full name are required.", "error")
                return render_template("student_form.html", student=student), 400

            student.student_code = student_code
            student.full_name = full_name
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                flash(
                    "That student code is already in use. Choose another code.",
                    "error",
                )
                return render_template("student_form.html", student=student), 409

            flash("Student details updated.", "success")
            return redirect(url_for("students.list_students"))

        return render_template("student_form.html", student=student)


@students_bp.route("/<int:student_id>/delete", methods=["POST"])
@role_required("faculty")
def delete_student(student_id):
    """Delete an unreferenced student without cascading academic history."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        student = session.get(Student, student_id)
        if student is None:
            return "Student not found.", 404

        has_enrollment = session.scalar(
            select(StudentCourse.id)
            .where(StudentCourse.student_id == student_id)
            .limit(1)
        )
        has_attendance = session.scalar(
            select(AttendanceEntry.id)
            .where(AttendanceEntry.student_id == student_id)
            .limit(1)
        )
        has_mark = session.scalar(
            select(AssessmentMark.id)
            .where(AssessmentMark.student_id == student_id)
            .limit(1)
        )
        has_login = session.scalar(
            select(User.id)
            .where(User.student_id == student_id)
            .limit(1)
        )
        if any((has_enrollment, has_attendance, has_mark, has_login)):
            flash(
                "This student cannot be deleted while enrollments, a student login, "
                "attendance, assessment marks, academic records, or support follow-ups "
                "are linked. Remove eligible empty enrollments first; academic history "
                "must be retained.",
                "error",
            )
            return redirect(url_for("students.list_students"))

        session.delete(student)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            flash(
                "The student could not be deleted because related records were added. "
                "Refresh the directory and review the linked data.",
                "error",
            )
            return redirect(url_for("students.list_students"))

    flash("Student deleted.", "success")
    return redirect(url_for("students.list_students"))
