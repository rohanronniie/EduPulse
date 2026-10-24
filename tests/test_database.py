
import pytest

from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import Course, Student, StudentCourse


def create_test_session():
    """Create an isolated in-memory SQLite database for a test."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def enable_test_foreign_keys(dbapi_connection, connection_record):
        """Enable foreign-key enforcement in the test database."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)

    TestSession = sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
    )

    return TestSession()


def test_student_can_be_created():
    session = create_test_session()

    try:
        student = Student(
            student_code="TEST001",
            full_name="Test Student",
        )
        session.add(student)
        session.commit()

        saved_student = session.query(Student).filter_by(
            student_code="TEST001"
        ).first()

        assert saved_student is not None
        assert saved_student.full_name == "Test Student"
        assert saved_student.id is not None
        assert saved_student.created_at is not None
    finally:
        session.close()


def test_duplicate_student_code_is_rejected():
    session = create_test_session()

    try:
        session.add(
            Student(
                student_code="TEST001",
                full_name="Student One",
            )
        )
        session.commit()

        session.add(
            Student(
                student_code="TEST001",
                full_name="Student Two",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()
    finally:
        session.close()


def test_blank_student_code_is_rejected():
    with pytest.raises(ValueError, match="student_code"):
        Student(
            student_code="   ",
            full_name="Test Student",
        )


def test_blank_student_name_is_rejected():
    with pytest.raises(ValueError, match="full_name"):
        Student(
            student_code="TEST002",
            full_name="   ",
        )


def test_course_and_student_enrollment():
    session = create_test_session()

    try:
        student = Student(
            student_code="TEST003",
            full_name="Enrollment Student",
        )
        course = Course(
            course_code="CS101",
            title="Introduction to Computer Science",
        )

        session.add_all([student, course])
        session.flush()

        enrollment = StudentCourse(
            student_id=student.id,
            course_id=course.id,
        )
        session.add(enrollment)
        session.commit()

        assert len(student.enrollments) == 1
        assert student.enrollments[0].course.title == (
            "Introduction to Computer Science"
        )
        assert course.enrollments[0].student.full_name == (
            "Enrollment Student"
        )
    finally:
        session.close()


def test_duplicate_enrollment_is_rejected():
    session = create_test_session()

    try:
        student = Student(
            student_code="TEST004",
            full_name="Duplicate Enrollment Student",
        )
        course = Course(
            course_code="CS102",
            title="Database Systems",
        )

        session.add_all([student, course])
        session.flush()

        session.add(
            StudentCourse(
                student_id=student.id,
                course_id=course.id,
            )
        )
        session.commit()

        session.add(
            StudentCourse(
                student_id=student.id,
                course_id=course.id,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()
    finally:
        session.close()


def test_enrollment_rejects_nonexistent_student():
    session = create_test_session()

    try:
        course = Course(
            course_code="CS103",
            title="Operating Systems",
        )
        session.add(course)
        session.flush()

        session.add(
            StudentCourse(
                student_id=9999,
                course_id=course.id,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()
    finally:
        session.close()
