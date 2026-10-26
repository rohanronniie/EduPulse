
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

from src.auth_routes import role_required
from src.academic_engine import (
    compare_academic_scenarios,
    generate_academic_report,
    recommend_interventions,
)
from src.academic_models import AcademicRecord
from src.models import Course, Student, StudentCourse


academic_bp = Blueprint("academic", __name__, url_prefix="/academic")


@academic_bp.route("/records")
@role_required("faculty")
def list_records():
    """List saved academic records."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        records = session.scalars(
            select(AcademicRecord).order_by(AcademicRecord.id.desc())
        ).all()

        rows = []
        for record in records:
            enrollment = session.get(StudentCourse, record.student_course_id)
            student = session.get(Student, enrollment.student_id)
            course = session.get(Course, enrollment.course_id)

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
    """Create academic data for a student-course enrollment."""
    session_factory = current_app.config["SESSION_FACTORY"]

    if request.method == "POST":
        enrollment_id = request.form.get("enrollment_id", type=int)
        attendance_text = request.form.get(
            "attendance_percentage", ""
        ).strip()
        scores_text = request.form.get("assessment_scores", "").strip()
        completed_text = request.form.get(
            "completed_assignments", ""
        ).strip()
        total_text = request.form.get("total_assignments", "").strip()

        try:
            attendance = float(attendance_text)
            scores = [
                float(item.strip())
                for item in scores_text.split(",")
                if item.strip()
            ]
            completed = int(completed_text)
            total = int(total_text)

            generate_academic_report(
                attendance, scores, completed, total
            )

        except (ValueError, TypeError) as exc:
            flash(f"Please check the academic data: {exc}", "error")
            return redirect(url_for("academic.create_record"))

        with session_factory() as session:
            enrollments = session.scalars(
                select(StudentCourse).order_by(StudentCourse.id)
            ).all()

            if (
                not enrollment_id
                or session.get(StudentCourse, enrollment_id) is None
            ):
                flash("Select a valid student-course enrollment.", "error")
                return render_template(
                    "academic_record_form.html",
                    enrollments=enrollments,
                ), 400

            record = AcademicRecord(
                student_course_id=enrollment_id,
                attendance_percentage=attendance,
                assessment_scores=scores,
                completed_assignments=completed,
                total_assignments=total,
            )
            session.add(record)

            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                flash(
                    "Academic data already exists for this enrollment.",
                    "error",
                )
                return render_template(
                    "academic_record_form.html",
                    enrollments=enrollments,
                ), 409

        flash("Academic record saved successfully.", "success")
        return redirect(url_for("academic.list_records"))

    with session_factory() as session:
        enrollments = session.scalars(
            select(StudentCourse).order_by(StudentCourse.id)
        ).all()

        choices = []
        for enrollment in enrollments:
            student = session.get(Student, enrollment.student_id)
            course = session.get(Course, enrollment.course_id)
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
    """Generate an explainable report from a saved academic record."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        record = session.get(AcademicRecord, record_id)

        if record is None:
            return "Academic record not found", 404

        enrollment = session.get(StudentCourse, record.student_course_id)
        student = session.get(Student, enrollment.student_id)
        course = session.get(Course, enrollment.course_id)

        data = {
            "record_id": record.id,
            "student_code": student.student_code,
            "student_name": student.full_name,
            "course_code": course.course_code,
            "course_title": course.title,
            "attendance": record.attendance_percentage,
            "scores": record.assessment_scores,
            "completed": record.completed_assignments,
            "total": record.total_assignments,
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
    """Compare saved academic data with a hypothetical scenario."""
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as session:
        record = session.get(AcademicRecord, record_id)

        if record is None:
            return "Academic record not found", 404

        enrollment = session.get(StudentCourse, record.student_course_id)
        student = session.get(Student, enrollment.student_id)
        course = session.get(Course, enrollment.course_id)

        current_scenario = {
            "attendance_percentage": record.attendance_percentage,
            "assessment_scores": list(record.assessment_scores),
            "completed_assignments": record.completed_assignments,
            "total_assignments": record.total_assignments,
        }

        data = {
            "record_id": record.id,
            "student_name": student.full_name,
            "course_code": course.course_code,
            "course_title": course.title,
        }

    result = None
    form_values = {
        "attendance_percentage": current_scenario["attendance_percentage"],
        "assessment_scores": ", ".join(
            str(score) for score in current_scenario["assessment_scores"]
        ),
        "completed_assignments": current_scenario["completed_assignments"],
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
            hypothetical_scenario = {
                "attendance_percentage": float(
                    form_values["attendance_percentage"]
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
