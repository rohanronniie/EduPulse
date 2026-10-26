
import pytest

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash

from src import create_app
from src.database import Base
from src.models import Course, Student, StudentCourse
from src.academic_models import AcademicRecord
from src.portal_models import User


def create_test_app():
    """Create an app backed by an isolated in-memory database."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)

    test_session_factory = sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
    )

    # Create a faculty account for authenticated route tests.
    with test_session_factory() as session:
        faculty = User(
            username="faculty.test",
            password_hash=generate_password_hash("TestFaculty@2026"),
            role="faculty",
        )
        session.add(faculty)
        session.commit()

    app = create_app(
        {
            "TESTING": True,
            "INITIALIZE_DATABASE": False,
            "SESSION_FACTORY": test_session_factory,
            "SECRET_KEY": "test-secret",
        }
    )

    return app, test_engine


def login_as_faculty(client):
    """Log in using the faculty account created for the test database."""
    response = client.post(
        "/login",
        data={
            "username": "faculty.test",
            "password": "TestFaculty@2026",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    return response


def login_as_student(client, test_engine):
    """Create and log in a student account for access-control tests."""
    with sessionmaker(bind=test_engine)() as session:
        student = Student(
            student_code="ROLE001",
            full_name="Role Test Student",
        )
        session.add(student)
        session.flush()

        student_user = User(
            username="student.test",
            password_hash=generate_password_hash("TestStudent@2026"),
            role="student",
            student_id=student.id,
        )
        session.add(student_user)
        session.commit()

    return client.post(
        "/login",
        data={
            "username": "student.test",
            "password": "TestStudent@2026",
        },
        follow_redirects=True,
    )


def test_homepage_loads():
    app = create_app(
        {
            "TESTING": True,
            "INITIALIZE_DATABASE": False,
            "SECRET_KEY": "test-secret",
        }
    )
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_health_endpoint():
    app = create_app(
        {
            "TESTING": True,
            "INITIALIZE_DATABASE": False,
        }
    )
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json["status"] == "healthy"
    assert response.json["application"] == "EduPulse"


def test_student_management_requires_login():
    app, test_engine = create_test_app()

    try:
        response = app.test_client().get("/students/")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
    finally:
        test_engine.dispose()


def test_student_cannot_access_student_management():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_student(client, test_engine)

        response = client.get("/students/")

        assert response.status_code == 302
    finally:
        test_engine.dispose()


def test_student_registration_saves_student():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)

        response = client.post(
            "/students/new",
            data={
                "student_code": "WEB001",
                "full_name": "Web Test Student",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Student registered successfully." in response.data
        assert b"WEB001" in response.data
        assert b"Web Test Student" in response.data

        with sessionmaker(bind=test_engine)() as session:
            student = session.scalar(
                select(Student).where(Student.student_code == "WEB001")
            )
            assert student is not None
            assert student.full_name == "Web Test Student"
    finally:
        test_engine.dispose()


def test_duplicate_student_registration_is_rejected():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)

        first_response = client.post(
            "/students/new",
            data={
                "student_code": "WEB002",
                "full_name": "First Student",
            },
        )
        assert first_response.status_code == 302

        second_response = client.post(
            "/students/new",
            data={
                "student_code": "WEB002",
                "full_name": "Second Student",
            },
        )

        assert second_response.status_code == 409
        assert b"student code already exists" in second_response.data
    finally:
        test_engine.dispose()


def test_blank_student_registration_is_rejected():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)

        response = client.post(
            "/students/new",
            data={
                "student_code": "   ",
                "full_name": "Test Student",
            },
        )

        assert response.status_code == 200
        assert b"Student code and full name are required." in response.data
    finally:
        test_engine.dispose()


def test_course_creation_saves_course():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)

        response = client.post(
            "/courses/new",
            data={
                "course_code": "CS101",
                "title": "Introduction to Computer Science",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Course created successfully." in response.data
        assert b"CS101" in response.data
        assert b"Introduction to Computer Science" in response.data

        with sessionmaker(bind=test_engine)() as session:
            course = session.scalar(
                select(Course).where(Course.course_code == "CS101")
            )
            assert course is not None
            assert course.title == "Introduction to Computer Science"
    finally:
        test_engine.dispose()


def test_duplicate_course_creation_is_rejected():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)
        
        first_response = client.post(
            "/courses/new",
            data={
                "course_code": "CS102",
                "title": "Database Systems",
            },
        )
        assert first_response.status_code == 302

        second_response = client.post(
            "/courses/new",
            data={
                "course_code": "CS102",
                "title": "Different Course Title",
            },
        )

        assert second_response.status_code == 409
        assert b"course code already exists" in second_response.data
    finally:
        test_engine.dispose()


def test_blank_course_fields_are_rejected():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)

        response = client.post(
            "/courses/new",
            data={
                "course_code": "   ",
                "title": "   ",
            },
        )

        assert response.status_code == 200
        assert b"Course code and title are required." in response.data
    finally:
        test_engine.dispose()


def test_enrollment_list_displays_student_and_course():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)

        with sessionmaker(bind=test_engine)() as session:
            student = Student(
                student_code="ENR001",
                full_name="Enrollment Test Student",
            )
            course = Course(
                course_code="ENR101",
                title="Enrollment Test Course",
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

        response = client.get("/enrollments/")

        assert response.status_code == 200
        assert b"ENR001" in response.data
        assert b"Enrollment Test Student" in response.data
        assert b"ENR101" in response.data
        assert b"Enrollment Test Course" in response.data
    finally:
        test_engine.dispose()


def test_academic_record_creation_and_report():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)

        with sessionmaker(bind=test_engine)() as session:
            student = Student(
                student_code="AC001",
                full_name="Academic Test Student",
            )
            course = Course(
                course_code="AC101",
                title="Academic Test Course",
            )
            session.add_all([student, course])
            session.flush()

            enrollment = StudentCourse(
                student_id=student.id,
                course_id=course.id,
            )
            session.add(enrollment)
            session.commit()
            enrollment_id = enrollment.id

        response = client.post(
            "/academic/records/new",
            data={
                "enrollment_id": str(enrollment_id),
                "attendance_percentage": "62",
                "assessment_scores": "82, 71, 58",
                "completed_assignments": "6",
                "total_assignments": "10",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Academic record saved successfully." in response.data
        assert b"AC001" in response.data
        assert b"AC101" in response.data

        with sessionmaker(bind=test_engine)() as session:
            record = session.query(AcademicRecord).one()
            record_id = record.id

            assert record.attendance_percentage == 62
            assert record.assessment_scores == [82, 71, 58]
            assert record.completed_assignments == 6
            assert record.total_assignments == 10

        report_response = client.get(
            f"/academic/records/{record_id}/report"
        )

        assert report_response.status_code == 200
        assert b"Academic Support Report" in report_response.data
        assert b"Attendance" in report_response.data
        assert b"Assessment Trend" in report_response.data
        assert b"Assignment Completion" in report_response.data
    finally:
        test_engine.dispose()


def test_what_if_comparison_does_not_modify_saved_record():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)
        
        with sessionmaker(bind=test_engine)() as session:
            student = Student(
                student_code="WF001",
                full_name="What If Test Student",
            )
            course = Course(
                course_code="WF101",
                title="What If Test Course",
            )
            session.add_all([student, course])
            session.flush()

            enrollment = StudentCourse(
                student_id=student.id,
                course_id=course.id,
            )
            session.add(enrollment)
            session.flush()

            record = AcademicRecord(
                student_course_id=enrollment.id,
                attendance_percentage=62,
                assessment_scores=[82, 71, 58],
                completed_assignments=6,
                total_assignments=10,
            )
            session.add(record)
            session.commit()
            record_id = record.id

        response = client.post(
            f"/academic/records/{record_id}/what-if",
            data={
                "attendance_percentage": "80",
                "assessment_scores": "82, 78, 85",
                "completed_assignments": "9",
                "total_assignments": "10",
            },
        )

        assert response.status_code == 200
        assert b"Comparison Results" in response.data
        assert b"Current Scenario" in response.data
        assert b"Hypothetical Scenario" in response.data

        with sessionmaker(bind=test_engine)() as session:
            saved_record = session.get(AcademicRecord, record_id)

            assert saved_record.attendance_percentage == 62
            assert saved_record.assessment_scores == [82, 71, 58]
            assert saved_record.completed_assignments == 6
            assert saved_record.total_assignments == 10
    finally:
        test_engine.dispose()


def test_academic_report_returns_404_for_missing_record():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)
        
        response = client.get("/academic/records/9999/report")

        assert response.status_code == 404
    finally:
        test_engine.dispose()
