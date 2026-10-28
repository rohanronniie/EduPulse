
import json

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

from src.auth_routes import get_current_user, role_required
from src.academic_engine import (
    compare_academic_scenarios,
    generate_academic_report,
    recommend_interventions,
)
from src.academic_models import AcademicRecord
from src.models import Course, Student, StudentCourse
from src.portal_models import (
    Assessment,
    AssessmentMark,
    AttendanceEntry,
    AttendanceSession,
    FacultyCourse,
)


academic_bp = Blueprint("academic", __name__, url_prefix="/academic")


def _get_assigned_enrollment(db, enrollment_id, faculty_id):
    """Return an enrollment only if the faculty member owns its course."""
    return db.scalar(
        select(StudentCourse)
        .join(Course, Course.id == StudentCourse.course_id)
        .join(FacultyCourse, FacultyCourse.course_id == Course.id)
        .where(
            StudentCourse.id == enrollment_id,
            FacultyCourse.faculty_id == faculty_id,
        )
    )


def _get_live_academic_data(db, enrollment, record):
    """
    Build a scenario using live attendance and published assessment marks.

    Saved academic values are retained as fallbacks when live data is absent.
    Assignment completion always comes from the saved academic record.
    """
    student = db.get(Student, enrollment.student_id)
    course = db.get(Course, enrollment.course_id)

    if student is None or course is None:
        return None

    # Attendance for this student and course only.
    attendance_rows = db.execute(
        select(AttendanceEntry.status)
        .join(
            AttendanceSession,
            AttendanceSession.id == AttendanceEntry.session_id,
        )
        .where(
            AttendanceSession.course_id == course.id,
            AttendanceEntry.student_id == student.id,
        )
    ).all()

    if attendance_rows:
        attended = sum(
            status in ("present", "late")
            for (status,) in attendance_rows
        )
        attendance = attended / len(attendance_rows) * 100
        attendance_source = "Live attendance records"
    elif record is not None:
        attendance = record.attendance_percentage
        attendance_source = "Saved academic record (fallback)"
    else:
        attendance = None
        attendance_source = "No attendance data available"

    # Published assessments only, ordered chronologically.
    published_marks = db.execute(
        select(AssessmentMark.marks, Assessment.max_marks)
        .join(
            Assessment,
            Assessment.id == AssessmentMark.assessment_id,
        )
        .where(
            Assessment.course_id == course.id,
            AssessmentMark.student_id == student.id,
            Assessment.published.is_(True),
        )
        .order_by(Assessment.assessment_date, Assessment.id)
    ).all()

    if published_marks:
        scores = [
            round((marks / max_marks) * 100, 2)
            for marks, max_marks in published_marks
        ]
        assessment_source = "Published portal assessments"
    elif record is not None:
        scores = list(record.assessment_scores)
        assessment_source = "Saved academic record (fallback)"
    else:
        scores = []
        assessment_source = "No published assessment data available"

    # Assignment data is maintained in the academic record.
    if record is not None:
        completed = record.completed_assignments
        total = record.total_assignments
        assignment_source = "Saved academic record"
    else:
        completed = 0
        total = 0
        assignment_source = "No assignment record available"

    scenario = {
        "attendance_percentage": attendance,
        "assessment_scores": scores,
        "completed_assignments": completed,
        "total_assignments": total,
    }

    return {
        "student": student,
        "course": course,
        "scenario": scenario,
        "attendance_source": attendance_source,
        "assessment_source": assessment_source,
        "assignment_source": assignment_source,
    }


@academic_bp.route("/records")
@role_required("faculty")
def list_records():
    """List academic records belonging to assigned courses."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        records = db.scalars(
            select(AcademicRecord)
            .join(
                StudentCourse,
                StudentCourse.id == AcademicRecord.student_course_id,
            )
            .join(
                FacultyCourse,
                FacultyCourse.course_id == StudentCourse.course_id,
            )
            .where(FacultyCourse.faculty_id == user["id"])
            .order_by(AcademicRecord.id.desc())
        ).all()

        rows = []

        for record in records:
            enrollment = db.get(
                StudentCourse,
                record.student_course_id,
            )
            if enrollment is None:
                continue

            student = db.get(Student, enrollment.student_id)
            course = db.get(Course, enrollment.course_id)

            if student is None or course is None:
                continue

            rows.append({
                "record_id": record.id,
                "student_code": student.student_code,
                "student_name": student.full_name,
                "course_code": course.course_code,
                "course_title": course.title,
                "attendance": record.attendance_percentage,
                "scores": record.assessment_scores,
                "completed": record.completed_assignments,
                "total": record.total_assignments,
            })

    return render_template("academic_records.html", records=rows)


@academic_bp.route("/records/new", methods=["GET", "POST"])
@role_required("faculty")
def create_record():
    """Create academic data for an enrollment in an assigned course."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    if request.method == "POST":
        enrollment_id = request.form.get("enrollment_id", type=int)
        attendance_text = request.form.get(
            "attendance_percentage", ""
        ).strip()
        scores_text = request.form.get(
            "assessment_scores", ""
        ).strip()
        completed_text = request.form.get(
            "completed_assignments", ""
        ).strip()
        total_text = request.form.get(
            "total_assignments", ""
        ).strip()

        try:
            attendance = float(attendance_text)
            scores = [
                float(item.strip())
                for item in scores_text.split(",")
                if item.strip()
            ]
            completed = int(completed_text)
            total = int(total_text)

            # Reuse engine validation before saving.
            generate_academic_report(
                attendance,
                scores,
                completed,
                total,
            )

        except (ValueError, TypeError) as exc:
            flash(f"Please check the academic data: {exc}", "error")
            return redirect(url_for("academic.create_record"))

        with session_factory() as db:
            enrollments = db.scalars(
                select(StudentCourse)
                .join(
                    FacultyCourse,
                    FacultyCourse.course_id == StudentCourse.course_id,
                )
                .where(FacultyCourse.faculty_id == user["id"])
                .order_by(StudentCourse.id)
            ).all()

            if not enrollment_id:
                flash("Select a valid enrollment.", "error")
                return redirect(url_for("academic.create_record"))

            enrollment = _get_assigned_enrollment(
                db,
                enrollment_id,
                user["id"],
            )

            if enrollment is None:
                flash("Select an enrollment in your assigned courses.", "error")
                return redirect(url_for("academic.create_record"))

            record = AcademicRecord(
                student_course_id=enrollment_id,
                attendance_percentage=attendance,
                assessment_scores=scores,
                completed_assignments=completed,
                total_assignments=total,
            )
            db.add(record)

            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                flash(
                    "Academic data already exists for this enrollment.",
                    "error",
                )
                return redirect(url_for("academic.create_record"))

        flash("Academic record saved successfully.", "success")
        return redirect(url_for("academic.list_records"))

    with session_factory() as db:
        enrollments = db.scalars(
            select(StudentCourse)
            .join(
                FacultyCourse,
                FacultyCourse.course_id == StudentCourse.course_id,
            )
            .where(FacultyCourse.faculty_id == user["id"])
            .order_by(StudentCourse.id)
        ).all()

        choices = []

        for enrollment in enrollments:
            student = db.get(Student, enrollment.student_id)
            course = db.get(Course, enrollment.course_id)

            if student is None or course is None:
                continue

            choices.append({
                "id": enrollment.id,
                "label": (
                    f"{student.student_code} — {student.full_name} / "
                    f"{course.course_code} — {course.title}"
                ),
            })

    return render_template(
        "academic_record_form.html",
        enrollments=choices,
    )


@academic_bp.route("/records/<int:record_id>/report")
@role_required("faculty")
def academic_report(record_id):
    """Generate an explainable report using live portal data."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        record = db.get(AcademicRecord, record_id)

        if record is None:
            return "Academic record not found", 404

        enrollment = db.get(
            StudentCourse,
            record.student_course_id,
        )

        if enrollment is None:
            return "Academic record not found", 404

        # Do not reveal whether an inaccessible record exists.
        if _get_assigned_enrollment(
            db,
            enrollment.id,
            user["id"],
        ) is None:
            return "Academic record not found", 404

        live_data = _get_live_academic_data(
            db,
            enrollment,
            record,
        )

        if live_data is None:
            return "Student or course not found", 404

        scenario = live_data["scenario"]
        student = live_data["student"]
        course = live_data["course"]

        data = {
            "record_id": record.id,
            "student_code": student.student_code,
            "student_name": student.full_name,
            "course_code": course.course_code,
            "course_title": course.title,
            "attendance": scenario["attendance_percentage"],
            "scores": scenario["assessment_scores"],
            "completed": scenario["completed_assignments"],
            "total": scenario["total_assignments"],
            "attendance_source": live_data["attendance_source"],
            "assessment_source": live_data["assessment_source"],
            "assignment_source": live_data["assignment_source"],
        }

    report = generate_academic_report(
        data["attendance"],
        data["scores"],
        data["completed"],
        data["total"],
    )
    interventions = recommend_interventions(report)

    return render_template(
        "academic_report.html",
        data=data,
        report=report,
        interventions=interventions,
    )


@academic_bp.route(
    "/records/<int:record_id>/what-if",
    methods=["GET", "POST"],
)
@role_required("faculty")
def what_if(record_id):
    """Compare the current academic data with a hypothetical scenario."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        record = db.get(AcademicRecord, record_id)

        if record is None:
            return "Academic record not found", 404

        enrollment = db.get(
            StudentCourse,
            record.student_course_id,
        )

        if enrollment is None:
            return "Academic record not found", 404

        if _get_assigned_enrollment(
            db,
            enrollment.id,
            user["id"],
        ) is None:
            return "Academic record not found", 404

        live_data = _get_live_academic_data(
            db,
            enrollment,
            record,
        )

        if live_data is None:
            return "Student or course not found", 404

        current_scenario = live_data["scenario"]
        student = live_data["student"]
        course = live_data["course"]

        data = {
            "record_id": record.id,
            "student_name": student.full_name,
            "course_code": course.course_code,
            "course_title": course.title,
            "attendance_source": live_data["attendance_source"],
            "assessment_source": live_data["assessment_source"],
            "assignment_source": live_data["assignment_source"],
        }

    result = None

    form_values = {
        "attendance_percentage": (
            current_scenario["attendance_percentage"]
            if current_scenario["attendance_percentage"] is not None
            else ""
        ),
        "assessment_scores": ", ".join(
            str(score)
            for score in current_scenario["assessment_scores"]
        ),
        "completed_assignments": current_scenario[
            "completed_assignments"
        ],
        "total_assignments": current_scenario["total_assignments"],
    }

    error = None

    if request.method == "POST":
        form_values = {
            "attendance_percentage": request.form.get(
                "attendance_percentage", ""
            ).strip(),
            "assessment_scores": request.form.get(
                "assessment_scores", ""
            ).strip(),
            "completed_assignments": request.form.get(
                "completed_assignments", ""
            ).strip(),
            "total_assignments": request.form.get(
                "total_assignments", ""
            ).strip(),
        }

        try:
            attendance_text = form_values["attendance_percentage"]

            hypothetical_scenario = {
                "attendance_percentage": (
                    float(attendance_text)
                    if attendance_text
                    else None
                ),
                "assessment_scores": [
                    float(score.strip())
                    for score in form_values["assessment_scores"].split(",")
                    if score.strip()
                ],
                "completed_assignments": int(
                    form_values["completed_assignments"]
                ),
                "total_assignments": int(
                    form_values["total_assignments"]
                ),
            }

            result = compare_academic_scenarios(
                current_scenario,
                hypothetical_scenario,
            )

        except (ValueError, TypeError) as exc:
            error = f"Please check your hypothetical values: {exc}"

    return render_template(
        "what_if.html",
        data=data,
        form_values=form_values,
        result=result,
        error=error,
    )
