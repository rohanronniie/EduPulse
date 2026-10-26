
from datetime import date

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

from src.auth_routes import get_current_user, role_required
from src.models import Course, Student, StudentCourse
from src.portal_models import (
    AttendanceEntry,
    AttendanceSession,
    FacultyCourse,
)

attendance_bp = Blueprint("attendance", __name__, url_prefix="/attendance")

VALID_STATUSES = {"present", "absent", "late"}


def get_assigned_course(db, faculty_id, course_id):
    """Return a course only when it belongs to the faculty member."""
    return db.scalar(
        select(Course)
        .join(FacultyCourse, FacultyCourse.course_id == Course.id)
        .where(
            Course.id == course_id,
            FacultyCourse.faculty_id == faculty_id,
        )
    )


@attendance_bp.route("/")
@role_required("faculty")
def list_courses():
    """List courses assigned to the logged-in faculty member."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        courses = db.scalars(
            select(Course)
            .join(FacultyCourse, FacultyCourse.course_id == Course.id)
            .where(FacultyCourse.faculty_id == user["id"])
            .order_by(Course.title)
        ).all()

        return render_template("attendance_courses.html", courses=courses)


@attendance_bp.route("/course/<int:course_id>", methods=["GET", "POST"])
@role_required("faculty")
def take_attendance(course_id):
    """Record attendance for enrolled students in an assigned course."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        course = get_assigned_course(db, user["id"], course_id)

        if course is None:
            return "Course not found or not assigned to this faculty member.", 404

        students = db.scalars(
            select(Student)
            .join(StudentCourse, StudentCourse.student_id == Student.id)
            .where(StudentCourse.course_id == course_id)
            .order_by(Student.full_name)
        ).all()

        if request.method == "GET":
            return render_template(
                "attendance_take.html",
                course=course,
                students=students,
                today=date.today().isoformat(),
            )

        if not students:
            flash("There are no enrolled students in this course.", "error")
            return redirect(url_for("attendance.list_courses"))

        session_date_value = request.form.get("session_date", "").strip()
        topic = request.form.get("topic", "").strip()

        try:
            session_date = date.fromisoformat(session_date_value)
        except ValueError:
            flash("Please provide a valid class date.", "error")
            return redirect(
                url_for("attendance.take_attendance", course_id=course_id)
            )

        if not session_date_value:
            flash("Please provide a class date.", "error")
            return redirect(
                url_for("attendance.take_attendance", course_id=course_id)
            )

        if len(topic) > 200:
            flash("The topic must be 200 characters or fewer.", "error")
            return redirect(
                url_for("attendance.take_attendance", course_id=course_id)
            )

        submitted_entries = []
        for student in students:
            status = request.form.get(
                f"status_{student.id}", "absent"
            ).strip().lower()

            if status not in VALID_STATUSES:
                flash("An invalid attendance status was submitted.", "error")
                return redirect(
                    url_for("attendance.take_attendance", course_id=course_id)
                )

            submitted_entries.append((student.id, status))

        attendance_session = AttendanceSession(
            course_id=course_id,
            faculty_id=user["id"],
            session_date=session_date,
            topic=topic,
        )
        db.add(attendance_session)
        db.flush()

        for student_id, status in submitted_entries:
            db.add(
                AttendanceEntry(
                    session_id=attendance_session.id,
                    student_id=student_id,
                    status=status,
                )
            )

        db.commit()

        flash(
            f"Attendance saved for {len(submitted_entries)} students.",
            "success",
        )
        return redirect(url_for("attendance.list_courses"))
