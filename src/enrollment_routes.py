
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

from src.auth_routes import role_required
from src.academic_models import AcademicRecord
from src.models import Course, Student, StudentCourse
from src.portal_models import (
    Assessment,
    AssessmentMark,
    AttendanceEntry,
    AttendanceSession,
    SupportFollowUp,
)


enrollment_bp = Blueprint(
    "enrollment",
    __name__,
    url_prefix="/enrollments",
)


@enrollment_bp.route("/")
@role_required("faculty")
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
@role_required("faculty")
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


@enrollment_bp.route("/<int:enrollment_id>/delete", methods=["POST"])
@role_required("faculty")
def delete_enrollment(enrollment_id):
    """Remove an enrollment only if no academic history is attached to it."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        enrollment = session.scalar(
            select(StudentCourse)
            .options(
                joinedload(StudentCourse.student),
                joinedload(StudentCourse.course),
            )
            .where(StudentCourse.id == enrollment_id)
        )
        if enrollment is None:
            return "Enrollment not found.", 404

        student_id = enrollment.student_id
        course_id = enrollment.course_id
        has_academic_record = session.scalar(
            select(AcademicRecord.id)
            .where(AcademicRecord.student_course_id == enrollment_id)
            .limit(1)
        )
        has_follow_up = session.scalar(
            select(SupportFollowUp.id)
            .where(SupportFollowUp.student_course_id == enrollment_id)
            .limit(1)
        )
        has_attendance = session.scalar(
            select(AttendanceEntry.id)
            .join(
                AttendanceSession,
                AttendanceSession.id == AttendanceEntry.session_id,
            )
            .where(
                AttendanceSession.course_id == course_id,
                AttendanceEntry.student_id == student_id,
            )
            .limit(1)
        )
        has_marks = session.scalar(
            select(AssessmentMark.id)
            .join(
                Assessment,
                Assessment.id == AssessmentMark.assessment_id,
            )
            .where(
                Assessment.course_id == course_id,
                AssessmentMark.student_id == student_id,
            )
            .limit(1)
        )

        if any((has_academic_record, has_follow_up, has_attendance, has_marks)):
            flash(
                "This enrollment cannot be removed because it has attendance, "
                "assessment marks, an academic record, or support follow-ups. "
                "Those records are retained and must not be orphaned.",
                "error",
            )
            return redirect(url_for("enrollment.list_enrollments"))

        session.delete(enrollment)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            flash(
                "The enrollment could not be removed because related records were "
                "added. Refresh the list and review the student and course data.",
                "error",
            )
            return redirect(url_for("enrollment.list_enrollments"))

    flash("Enrollment removed.", "success")
    return redirect(url_for("enrollment.list_enrollments"))
