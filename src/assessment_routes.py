
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
    Assessment,
    AssessmentMark,
    FacultyCourse,
)

assessment_bp = Blueprint(
    "assessment",
    __name__,
    url_prefix="/assessments",
)


def get_assigned_course(db, faculty_id, course_id):
    """Return a course only if it is assigned to this faculty member."""
    return db.scalar(
        select(Course)
        .join(FacultyCourse, FacultyCourse.course_id == Course.id)
        .where(
            Course.id == course_id,
            FacultyCourse.faculty_id == faculty_id,
        )
    )


def get_enrolled_students(db, course_id):
    """Return the current roster for a course."""
    return db.scalars(
        select(Student)
        .join(StudentCourse, StudentCourse.student_id == Student.id)
        .where(StudentCourse.course_id == course_id)
        .order_by(Student.full_name)
    ).all()


def get_assessment_for_faculty(db, assessment_id, faculty_id):
    """Return an assessment only if its course is assigned to the faculty."""
    return db.scalar(
        select(Assessment)
        .join(Course, Course.id == Assessment.course_id)
        .join(FacultyCourse, FacultyCourse.course_id == Course.id)
        .where(
            Assessment.id == assessment_id,
            FacultyCourse.faculty_id == faculty_id,
        )
    )


@assessment_bp.route("/")
@role_required("faculty")
def list_courses():
    """List courses assigned to the current faculty member."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        courses = db.scalars(
            select(Course)
            .join(FacultyCourse, FacultyCourse.course_id == Course.id)
            .where(FacultyCourse.faculty_id == user["id"])
            .order_by(Course.title)
        ).all()

        return render_template(
            "assessment_courses.html",
            courses=courses,
        )


@assessment_bp.route("/course/<int:course_id>", methods=["GET", "POST"])
@role_required("faculty")
def course_assessments(course_id):
    """Create assessments and list assessments for an assigned course."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        course = get_assigned_course(db, user["id"], course_id)

        if course is None:
            return "Course not found or not assigned to this faculty member.", 404

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            max_marks_value = request.form.get("max_marks", "").strip()
            assessment_date_value = request.form.get(
                "assessment_date", ""
            ).strip()

            if not title or len(title) > 150:
                flash(
                    "Enter an assessment title of 1–150 characters.",
                    "error",
                )
                return redirect(
                    url_for(
                        "assessment.course_assessments",
                        course_id=course_id,
                    )
                )

            try:
                max_marks = float(max_marks_value)
            except (TypeError, ValueError):
                max_marks = 0

            if not 0 < max_marks < float("inf"):
                flash("Maximum marks must be a positive finite number.", "error")
                return redirect(
                    url_for(
                        "assessment.course_assessments",
                        course_id=course_id,
                    )
                )

            try:
                assessment_date = date.fromisoformat(
                    assessment_date_value
                )
            except ValueError:
                flash("Enter a valid assessment date.", "error")
                return redirect(
                    url_for(
                        "assessment.course_assessments",
                        course_id=course_id,
                    )
                )

            if not assessment_date_value:
                flash("Enter an assessment date.", "error")
                return redirect(
                    url_for(
                        "assessment.course_assessments",
                        course_id=course_id,
                    )
                )

            db.add(
                Assessment(
                    course_id=course_id,
                    faculty_id=user["id"],
                    title=title,
                    max_marks=max_marks,
                    assessment_date=assessment_date,
                    published=False,
                )
            )
            db.commit()

            flash("Assessment created successfully.", "success")
            return redirect(
                url_for(
                    "assessment.course_assessments",
                    course_id=course_id,
                )
            )

        assessments = db.scalars(
            select(Assessment)
            .where(Assessment.course_id == course_id)
            .order_by(Assessment.assessment_date.desc(), Assessment.id.desc())
        ).all()

        return render_template(
            "assessment_course.html",
            course=course,
            assessments=assessments,
            today=date.today().isoformat(),
        )


@assessment_bp.route("/<int:assessment_id>/marks", methods=["GET", "POST"])
@role_required("faculty")
def enter_marks(assessment_id):
    """Enter or update marks for students enrolled in the assessment's course."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        assessment = get_assessment_for_faculty(
            db,
            assessment_id,
            user["id"],
        )

        if assessment is None:
            return "Assessment not found or course not assigned to this faculty member.", 404

        if assessment.published and request.method == "POST":
            flash(
                "Published results are locked against further mark changes.",
                "error",
            )
            return redirect(
                url_for(
                    "assessment.course_assessments",
                    course_id=assessment.course_id,
                )
            )

        students = get_enrolled_students(db, assessment.course_id)

        existing_marks = db.scalars(
            select(AssessmentMark).where(
                AssessmentMark.assessment_id == assessment.id
            )
        ).all()
        marks_by_student = {
            mark.student_id: mark for mark in existing_marks
        }

        if request.method == "POST":
            if not students:
                flash("Enroll students before entering marks.", "error")
                return redirect(
                    url_for(
                        "assessment.course_assessments",
                        course_id=assessment.course_id,
                    )
                )

            submitted_marks = []

            for student in students:
                raw_value = request.form.get(
                    f"marks_{student.id}", ""
                ).strip()

                try:
                    score = float(raw_value)
                except (TypeError, ValueError):
                    flash(
                        f"Enter a valid mark for {student.full_name}.",
                        "error",
                    )
                    return redirect(
                        url_for(
                            "assessment.enter_marks",
                            assessment_id=assessment.id,
                        )
                    )

                if (
                    score < 0
                    or score > assessment.max_marks
                    or score == float("inf")
                    or score == float("-inf")
                    or score != score
                ):
                    flash(
                        f"Marks for {student.full_name} must be between "
                        f"0 and {assessment.max_marks:g}.",
                        "error",
                    )
                    return redirect(
                        url_for(
                            "assessment.enter_marks",
                            assessment_id=assessment.id,
                        )
                    )

                submitted_marks.append((student.id, score))

            for student_id, score in submitted_marks:
                existing = marks_by_student.get(student_id)

                if existing is None:
                    db.add(
                        AssessmentMark(
                            assessment_id=assessment.id,
                            student_id=student_id,
                            marks=score,
                        )
                    )
                else:
                    existing.marks = score

            db.commit()
            flash("Student marks saved successfully.", "success")
            return redirect(
                url_for(
                    "assessment.course_assessments",
                    course_id=assessment.course_id,
                )
            )

        return render_template(
            "assessment_marks.html",
            assessment=assessment,
            course=db.get(Course, assessment.course_id),
            students=students,
            marks_by_student=marks_by_student,
        )


@assessment_bp.route("/<int:assessment_id>/publish", methods=["POST"])
@role_required("faculty")
def publish_results(assessment_id):
    """Publish results only when every currently enrolled student has a mark."""
    user = get_current_user()
    session_factory = current_app.config["SESSION_FACTORY"]

    with session_factory() as db:
        assessment = get_assessment_for_faculty(
            db,
            assessment_id,
            user["id"],
        )

        if assessment is None:
            return "Assessment not found or course not assigned to this faculty member.", 404

        if assessment.published:
            flash("These results are already published.", "error")
            return redirect(
                url_for(
                    "assessment.course_assessments",
                    course_id=assessment.course_id,
                )
            )

        students = get_enrolled_students(db, assessment.course_id)
        marks = db.scalars(
            select(AssessmentMark).where(
                AssessmentMark.assessment_id == assessment.id
            )
        ).all()

        marked_student_ids = {mark.student_id for mark in marks}
        enrolled_student_ids = {student.id for student in students}

        if not enrolled_student_ids:
            flash("Cannot publish results for a course with no enrolled students.", "error")
            return redirect(
                url_for(
                    "assessment.course_assessments",
                    course_id=assessment.course_id,
                )
            )

        if marked_student_ids != enrolled_student_ids:
            missing_count = len(enrolled_student_ids - marked_student_ids)
            flash(
                f"Results cannot be published yet. "
                f"{missing_count} enrolled student(s) still need marks.",
                "error",
            )
            return redirect(
                url_for(
                    "assessment.course_assessments",
                    course_id=assessment.course_id,
                )
            )

        assessment.published = True
        db.commit()

        flash("Assessment results published successfully.", "success")
        return redirect(
            url_for(
                "assessment.course_assessments",
                course_id=assessment.course_id,
            )
        )
