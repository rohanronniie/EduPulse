
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
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from src.models import Course, Student, StudentCourse


enrollment_bp = Blueprint(
    "enrollment",
    __name__,
    url_prefix="/enrollments",
)



@enrollment_bp.route("/")
def list_enrollments():
    """Display student-course enrollments."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        enrollments = session.scalars(
            select(StudentCourse)
            .options(
                joinedload(StudentCourse.student),
                joinedload(StudentCourse.course),
            )
            .order_by(StudentCourse.id)
        ).all()

    return render_template(
        "enrollments.html",
        enrollments=enrollments,
    )



@enrollment_bp.route("/new", methods=["GET", "POST"])
def create_enrollment():
    """Enroll a student in an existing course."""
    session_factory = current_app.config["SESSION_FACTORY"]

    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        course_id = request.form.get("course_id", type=int)

        with session_factory() as session:
            students = session.scalars(
                select(Student).order_by(Student.full_name)
            ).all()
            courses = session.scalars(
                select(Course).order_by(Course.course_code)
            ).all()

            if not student_id or not course_id:
                flash("Please select both a student and a course.", "error")
                return render_template(
                    "enrollment_form.html",
                    students=students,
                    courses=courses,
                )

            student = session.get(Student, student_id)
            course = session.get(Course, course_id)

            if student is None or course is None:
                flash("The selected student or course does not exist.", "error")
                return render_template(
                    "enrollment_form.html",
                    students=students,
                    courses=courses,
                ), 400

            enrollment = StudentCourse(
                student_id=student_id,
                course_id=course_id,
            )
            session.add(enrollment)

            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                flash(
                    "This student is already enrolled in that course.",
                    "error",
                )
                return render_template(
                    "enrollment_form.html",
                    students=students,
                    courses=courses,
                ), 409

        flash("Student enrolled successfully.", "success")
        return redirect(url_for("enrollment.list_enrollments"))

    with session_factory() as session:
        students = session.scalars(
            select(Student).order_by(Student.full_name)
        ).all()
        courses = session.scalars(
            select(Course).order_by(Course.course_code)
        ).all()

    return render_template(
        "enrollment_form.html",
        students=students,
        courses=courses,
    )
