
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from src.database import SessionLocal, initialize_database
from src.models import Course, Student, StudentCourse
from src.portal_models import (
    User,
    FacultyCourse,
    AttendanceSession,
    AttendanceEntry,
    Assessment,
    AssessmentMark,
)


STUDENT_USERNAME = "student.demo"
STUDENT_PASSWORD = "EduPulseStudent@2026"

FACULTY_USERNAME = "faculty.demo"
FACULTY_PASSWORD = "EduPulseFaculty@2026"


def seed_demo_data():
    """Create repeatable synthetic data for local demonstrations."""
    initialize_database()

    with SessionLocal() as db:
        student = db.scalar(
            select(Student).where(Student.student_code == "DEMO001")
        )
        if student is None:
            student = Student(
                student_code="DEMO001",
                full_name="Alex Morgan",
            )
            db.add(student)
            db.flush()

        course = db.scalar(
            select(Course).where(Course.course_code == "DEMO101")
        )
        if course is None:
            course = Course(
                course_code="DEMO101",
                title="Introduction to Computing",
            )
            db.add(course)
            db.flush()

        enrollment = db.scalar(
            select(StudentCourse).where(
                StudentCourse.student_id == student.id,
                StudentCourse.course_id == course.id,
            )
        )
        if enrollment is None:
            db.add(
                StudentCourse(
                    student_id=student.id,
                    course_id=course.id,
                )
            )

        student_user = db.scalar(
            select(User).where(User.username == STUDENT_USERNAME)
        )
        if student_user is None:
            student_user = User(
                username=STUDENT_USERNAME,
                password_hash=generate_password_hash(STUDENT_PASSWORD),
                role="student",
                student_id=student.id,
            )
            db.add(student_user)
            db.flush()
        else:
            if student_user.role != "student" or student_user.student_id != student.id:
                raise RuntimeError(
                    "Existing student demo account has unexpected ownership."
                )
            student_user.password_hash = generate_password_hash(STUDENT_PASSWORD)

        faculty_user = db.scalar(
            select(User).where(User.username == FACULTY_USERNAME)
        )
        if faculty_user is None:
            faculty_user = User(
                username=FACULTY_USERNAME,
                password_hash=generate_password_hash(FACULTY_PASSWORD),
                role="faculty",
            )
            db.add(faculty_user)
            db.flush()
        elif faculty_user.role != "faculty":
            raise RuntimeError(
                "Existing faculty demo account has an unexpected role."
            )
        else:
            faculty_user.password_hash = generate_password_hash(FACULTY_PASSWORD)

        assignment = db.scalar(
            select(FacultyCourse).where(
                FacultyCourse.faculty_id == faculty_user.id,
                FacultyCourse.course_id == course.id,
            )
        )
        if assignment is None:
            db.add(
                FacultyCourse(
                    faculty_id=faculty_user.id,
                    course_id=course.id,
                )
            )

        # Three synthetic class sessions make attendance calculations meaningful.
        statuses = ["present", "present", "absent"]
        for index, status in enumerate(statuses):
            session_date = date.today() - timedelta(days=2 - index)
            topic = f"Demo lecture {index + 1}"

            attendance_session = db.scalar(
                select(AttendanceSession).where(
                    AttendanceSession.course_id == course.id,
                    AttendanceSession.session_date == session_date,
                    AttendanceSession.topic == topic,
                )
            )

            if attendance_session is None:
                attendance_session = AttendanceSession(
                    course_id=course.id,
                    faculty_id=faculty_user.id,
                    session_date=session_date,
                    topic=topic,
                )
                db.add(attendance_session)
                db.flush()

            entry = db.scalar(
                select(AttendanceEntry).where(
                    AttendanceEntry.session_id == attendance_session.id,
                    AttendanceEntry.student_id == student.id,
                )
            )
            if entry is None:
                db.add(
                    AttendanceEntry(
                        session_id=attendance_session.id,
                        student_id=student.id,
                        status=status,
                    )
                )
            else:
                entry.status = status

        assessment = db.scalar(
            select(Assessment).where(
                Assessment.course_id == course.id,
                Assessment.title == "Demo Internal Assessment 1",
            )
        )
        if assessment is None:
            assessment = Assessment(
                course_id=course.id,
                faculty_id=faculty_user.id,
                title="Demo Internal Assessment 1",
                max_marks=25,
                assessment_date=date.today(),
                published=True,
            )
            db.add(assessment)
            db.flush()

        mark = db.scalar(
            select(AssessmentMark).where(
                AssessmentMark.assessment_id == assessment.id,
                AssessmentMark.student_id == student.id,
            )
        )
        if mark is None:
            db.add(
                AssessmentMark(
                    assessment_id=assessment.id,
                    student_id=student.id,
                    marks=19,
                )
            )
        else:
            mark.marks = 19

        db.commit()

    print("Synthetic EduPulse demo data is ready.")
    print(f"Student login: {STUDENT_USERNAME} / {STUDENT_PASSWORD}")
    print(f"Faculty login: {FACULTY_USERNAME} / {FACULTY_PASSWORD}")
    print("Use these accounts only in your local demo environment.")


if __name__ == "__main__":
    try:
        seed_demo_data()
    except IntegrityError as exc:
        raise SystemExit(
            "Demo seeding failed due to a database constraint. "
            "Inspect existing demo records before retrying."
        ) from exc
