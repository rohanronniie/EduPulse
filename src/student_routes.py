
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models import Student
from src.auth_routes import role_required


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
