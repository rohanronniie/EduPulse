import pytest

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash
from datetime import date

from src import create_app
from src.database import Base
from src.models import Course, Student, StudentCourse
from src.academic_models import AcademicRecord
from src.portal_models import (
    User,
    FacultyCourse,
    AttendanceSession,
    AttendanceEntry,
    Assessment,
    AssessmentMark,
)

    
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
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret",
        }
    )
    return app, test_engine



def login_as_faculty(client):
    """Log in as the faculty test user and retain a valid CSRF token."""
    import re

    login_page = client.get("/login")
    assert login_page.status_code == 200

    match = re.search(
        rb'name="csrf_token"\s+value="([^"]+)"',
        login_page.data,
    )
    assert match is not None, "Login page did not render a CSRF token."

    token = match.group(1).decode()
    client._csrf_token = token

    response = client.post(
        "/login",
        data={
            "username": "faculty.test",
            "password": "TestFaculty@2026",
            "csrf_token": token,
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
            "WTF_CSRF_ENABLED": False,
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

            faculty = session.query(User).filter_by(
                username="faculty.test"
            ).one()

            session.add(
                FacultyCourse(
                    faculty_id=faculty.id,
                    course_id=course.id,
                )
            )

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

            faculty = session.query(User).filter_by(
                username="faculty.test"
            ).one()

            session.add(
                FacultyCourse(
                    faculty_id=faculty.id,
                    course_id=course.id,
                )
            )

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


def create_assessment_fixture(test_engine):
    """Create an assigned course with two enrolled students."""
    with sessionmaker(bind=test_engine)() as session:
        faculty = session.scalar(
            select(User).where(User.username == "faculty.test")
        )

        course = Course(
            course_code="AS101",
            title="Assessment Test Course",
        )
        student_one = Student(
            student_code="AS001",
            full_name="Assessment Student One",
        )
        student_two = Student(
            student_code="AS002",
            full_name="Assessment Student Two",
        )

        session.add_all([course, student_one, student_two])
        session.flush()

        session.add_all([
            FacultyCourse(
                faculty_id=faculty.id,
                course_id=course.id,
            ),
            StudentCourse(
                student_id=student_one.id,
                course_id=course.id,
            ),
            StudentCourse(
                student_id=student_two.id,
                course_id=course.id,
            ),
        ])
        session.commit()

        return {
            "course_id": course.id,
            "student_one_id": student_one.id,
            "student_two_id": student_two.id,
        }


def test_assessment_creation_saves_assessment():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)
        ids = create_assessment_fixture(test_engine)

        response = client.post(
            f"/assessments/course/{ids['course_id']}",
            data={
                "title": "Internal Assessment 1",
                "max_marks": "30",
                "assessment_date": "2026-10-27",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Assessment created successfully." in response.data

        with sessionmaker(bind=test_engine)() as session:
            assessment = session.scalar(
                select(Assessment).where(
                    Assessment.title == "Internal Assessment 1"
                )
            )
            assert assessment is not None
            assert assessment.max_marks == 30
            assert assessment.published is False
    finally:
        test_engine.dispose()


def test_assessment_creation_rejects_invalid_maximum_marks():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)
        ids = create_assessment_fixture(test_engine)

        for invalid_maximum in ["0", "-10", "abc", "nan", "inf"]:
            response = client.post(
                f"/assessments/course/{ids['course_id']}",
                data={
                    "title": "Invalid Assessment",
                    "max_marks": invalid_maximum,
                    "assessment_date": "2026-10-27",
                },
                follow_redirects=True,
            )

            assert response.status_code == 200
            assert b"Maximum marks must be a positive finite number." in response.data

        with sessionmaker(bind=test_engine)() as session:
            count = session.scalar(
                select(__import__("sqlalchemy").func.count(Assessment.id))
            )
            assert count == 0
    finally:
        test_engine.dispose()


def test_faculty_cannot_manage_unassigned_course_assessments():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)

        with sessionmaker(bind=test_engine)() as session:
            course = Course(
                course_code="OTHER101",
                title="Unassigned Course",
            )
            session.add(course)
            session.commit()
            course_id = course.id

        response = client.get(f"/assessments/course/{course_id}")
        assert response.status_code == 404
    finally:
        test_engine.dispose()


def test_marks_are_saved_for_enrolled_students():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)
        ids = create_assessment_fixture(test_engine)

        with sessionmaker(bind=test_engine)() as session:
            assessment = Assessment(
                course_id=ids["course_id"],
                faculty_id=session.scalar(
                    select(User.id).where(User.username == "faculty.test")
                ),
                title="Marks Test",
                max_marks=30,
                assessment_date=date(2026, 10, 27),
                published=False,
            )
            session.add(assessment)
            session.commit()
            assessment_id = assessment.id

        response = client.post(
            f"/assessments/{assessment_id}/marks",
            data={
                f"marks_{ids['student_one_id']}": "25",
                f"marks_{ids['student_two_id']}": "18.5",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Student marks saved successfully." in response.data

        with sessionmaker(bind=test_engine)() as session:
            marks = session.scalars(
                select(AssessmentMark).where(
                    AssessmentMark.assessment_id == assessment_id
                )
            ).all()

            saved = {mark.student_id: mark.marks for mark in marks}
            assert saved[ids["student_one_id"]] == 25
            assert saved[ids["student_two_id"]] == 18.5
    finally:
        test_engine.dispose()


def test_invalid_marks_are_rejected_without_saving_any_marks():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)
        ids = create_assessment_fixture(test_engine)

        with sessionmaker(bind=test_engine)() as session:
            faculty_id = session.scalar(
                select(User.id).where(User.username == "faculty.test")
            )
            assessment = Assessment(
                course_id=ids["course_id"],
                faculty_id=faculty_id,
                title="Validation Test",
                max_marks=30,
                assessment_date=date(2026, 10, 27),
                published=False,
            )
            session.add(assessment)
            session.commit()
            assessment_id = assessment.id

        invalid_values = ["-1", "31", "abc", "nan", "inf"]

        for invalid_value in invalid_values:
            response = client.post(
                f"/assessments/{assessment_id}/marks",
                data={
                    f"marks_{ids['student_one_id']}": invalid_value,
                    f"marks_{ids['student_two_id']}": "20",
                },
                follow_redirects=True,
            )
            assert response.status_code == 200
            assert b"Enter a valid mark" in response.data or (
                b"must be between" in response.data
            )

        with sessionmaker(bind=test_engine)() as session:
            count = session.scalar(
                select(__import__("sqlalchemy").func.count(AssessmentMark.id))
            )
            assert count == 0
    finally:
        test_engine.dispose()


def test_results_cannot_be_published_with_missing_marks():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_faculty(client)
        ids = create_assessment_fixture(test_engine)

        with sessionmaker(bind=test_engine)() as session:
            faculty_id = session.scalar(
                select(User.id).where(User.username == "faculty.test")
            )
            assessment = Assessment(
                course_id=ids["course_id"],
                faculty_id=faculty_id,
                title="Incomplete Marks Test",
                max_marks=30,
                assessment_date=date(2026, 10, 27),
                published=False,
            )
            session.add(assessment)
            session.flush()

            session.add(
                AssessmentMark(
                    assessment_id=assessment.id,
                    student_id=ids["student_one_id"],
                    marks=20,
                )
            )
            session.commit()
            assessment_id = assessment.id

        response = client.post(
            f"/assessments/{assessment_id}/publish",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Results cannot be published yet." in response.data

        with sessionmaker(bind=test_engine)() as session:
            assessment = session.get(Assessment, assessment_id)
            assert assessment.published is False
    finally:
        test_engine.dispose()


def test_student_sees_published_marks_but_not_unpublished_marks():
    app, test_engine = create_test_app()

    try:
        ids = create_assessment_fixture(test_engine)

        with sessionmaker(bind=test_engine)() as session:
            student = session.get(Student, ids["student_one_id"])
            student_user = User(
                username="assessment.student",
                password_hash=generate_password_hash("StudentTest@2026"),
                role="student",
                student_id=student.id,
            )

            faculty_id = session.scalar(
                select(User.id).where(User.username == "faculty.test")
            )

            published = Assessment(
                course_id=ids["course_id"],
                faculty_id=faculty_id,
                title="Published Internal",
                max_marks=30,
                assessment_date=date(2026, 10, 27),
                published=True,
            )
            unpublished = Assessment(
                course_id=ids["course_id"],
                faculty_id=faculty_id,
                title="Draft Internal",
                max_marks=30,
                assessment_date=date(2026, 10, 28),
                published=False,
            )

            session.add_all([student_user, published, unpublished])
            session.flush()

            session.add_all([
                AssessmentMark(
                    assessment_id=published.id,
                    student_id=student.id,
                    marks=24,
                ),
                AssessmentMark(
                    assessment_id=unpublished.id,
                    student_id=student.id,
                    marks=29,
                ),
            ])
            session.commit()

        client = app.test_client()
        response = client.post(
            "/login",
            data={
                "username": "assessment.student",
                "password": "StudentTest@2026",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Published Internal" in response.data
        assert b"Draft Internal" not in response.data
    finally:
        test_engine.dispose()


# ---------------------------------------------------------
# Analytics dashboard tests
# ---------------------------------------------------------

def create_analytics_fixture(test_engine):
    """Create a course, enrolled student, and faculty assignment."""
    with sessionmaker(bind=test_engine, expire_on_commit=False)() as session:
        faculty = session.scalar(
            select(User).where(User.username == "faculty.test")
        )

        student = Student(
            student_code="ANALYTICS001",
            full_name="Analytics Test Student",
        )
        course = Course(
            course_code="ANL101",
            title="Analytics Fundamentals",
        )

        session.add_all([student, course])
        session.flush()

        session.add_all([
            StudentCourse(
                student_id=student.id,
                course_id=course.id,
            ),
            FacultyCourse(
                faculty_id=faculty.id,
                course_id=course.id,
            ),
        ])
        session.commit()

        return {
            "faculty_id": faculty.id,
            "student_id": student.id,
            "course_id": course.id,
        }


def test_analytics_requires_login():
    app, test_engine = create_test_app()

    try:
        response = app.test_client().get("/analytics/")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
    finally:
        test_engine.dispose()


def test_student_cannot_access_analytics():
    app, test_engine = create_test_app()

    try:
        client = app.test_client()
        login_as_student(client, test_engine)

        response = client.get("/analytics/")

        assert response.status_code == 302
        assert "/login" in response.headers["Location"] or (
            response.headers["Location"].endswith("/")
        )
    finally:
        test_engine.dispose()


def test_analytics_only_shows_assigned_courses():
    app, test_engine = create_test_app()

    try:
        ids = create_analytics_fixture(test_engine)
        client = app.test_client()
        login_as_faculty(client)

        response = client.get("/analytics/")

        assert response.status_code == 200
        assert b"Analytics Fundamentals" in response.data

        with sessionmaker(bind=test_engine)() as session:
            other_course = Course(
                course_code="OTHER101",
                title="Unassigned Course",
            )
            session.add(other_course)
            session.commit()

        response = client.get("/analytics/")

        assert response.status_code == 200
        assert b"Analytics Fundamentals" in response.data
        assert b"Unassigned Course" not in response.data
    finally:
        test_engine.dispose()


def test_analytics_calculates_attendance_percentage():
    app, test_engine = create_test_app()

    try:
        ids = create_analytics_fixture(test_engine)

        with sessionmaker(bind=test_engine)() as session:
            attendance_session = AttendanceSession(
                course_id=ids["course_id"],
                faculty_id=ids["faculty_id"],
                session_date=date(2026, 10, 20),
                topic="Analytics test class",
            )
            session.add(attendance_session)
            session.flush()

            session.add(
                AttendanceEntry(
                    session_id=attendance_session.id,
                    student_id=ids["student_id"],
                    status="present",
                )
            )

            second_session = AttendanceSession(
                course_id=ids["course_id"],
                faculty_id=ids["faculty_id"],
                session_date=date(2026, 10, 21),
                topic="Analytics test class 2",
            )
            session.add(second_session)
            session.flush()

            session.add(
                AttendanceEntry(
                    session_id=second_session.id,
                    student_id=ids["student_id"],
                    status="absent",
                )
            )
            session.commit()

        client = app.test_client()
        login_as_faculty(client)

        response = client.get("/analytics/")

        assert response.status_code == 200
        assert b"50.0%" in response.data
    finally:
        test_engine.dispose()


def test_analytics_uses_published_assessments_only():
    app, test_engine = create_test_app()

    try:
        ids = create_analytics_fixture(test_engine)

        with sessionmaker(bind=test_engine)() as session:
            published = Assessment(
                course_id=ids["course_id"],
                faculty_id=ids["faculty_id"],
                title="Published Test",
                max_marks=100,
                assessment_date=date(2026, 10, 20),
                published=True,
            )
            unpublished = Assessment(
                course_id=ids["course_id"],
                faculty_id=ids["faculty_id"],
                title="Draft Test",
                max_marks=100,
                assessment_date=date(2026, 10, 21),
                published=False,
            )
            session.add_all([published, unpublished])
            session.flush()

            session.add_all([
                AssessmentMark(
                    assessment_id=published.id,
                    student_id=ids["student_id"],
                    marks=80,
                ),
                AssessmentMark(
                    assessment_id=unpublished.id,
                    student_id=ids["student_id"],
                    marks=10,
                ),
            ])
            session.commit()

        client = app.test_client()
        login_as_faculty(client)

        response = client.get("/analytics/")

        assert response.status_code == 200
        assert b"Published Test" not in response.data
        assert b"Draft Test" not in response.data
        assert b"80.0%" in response.data
        assert b"10.0%" not in response.data
    finally:
        test_engine.dispose()


def test_analytics_handles_missing_attendance_and_marks():
    app, test_engine = create_test_app()

    try:
        create_analytics_fixture(test_engine)

        client = app.test_client()
        login_as_faculty(client)

        response = client.get("/analytics/")

        assert response.status_code == 200
        assert b"Analytics Fundamentals" in response.data
        assert b"No data" in response.data
        assert b"No published marks" in response.data
    finally:
        test_engine.dispose()