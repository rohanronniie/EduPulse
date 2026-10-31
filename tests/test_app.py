import re

import pytest

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from werkzeug.security import generate_password_hash
from datetime import date

from src import create_app
from src.database import Base, DATABASE_PATH, resolve_database_url
from src.models import Course, Student, StudentCourse
from src.academic_models import AcademicRecord
from src.portal_models import (
    User,
    FacultyCourse,
    AttendanceSession,
    AttendanceEntry,
    Assessment,
    AssessmentMark,
    SupportFollowUp,
)


def test_database_url_defaults_to_sqlite_when_environment_value_is_blank():
    fallback_url = f"sqlite:///{DATABASE_PATH.as_posix()}"

    assert resolve_database_url({}) == fallback_url
    assert resolve_database_url({"EDUPULSE_DATABASE_URL": ""}) == fallback_url
    assert resolve_database_url({"EDUPULSE_DATABASE_URL": "   "}) == fallback_url


def test_database_url_normalizes_postgresql_scheme():
    assert (
        resolve_database_url(
            {"EDUPULSE_DATABASE_URL": "postgresql://user:pass@db.example/app"}
        )
        == "postgresql+psycopg://user:pass@db.example/app"
    )


def test_sign_in_page_offers_password_toggle_and_seeded_demo_accounts():
    app, test_engine = create_test_app()

    try:
        with sessionmaker(bind=test_engine)() as session:
            student = Student(
                student_code="DEMO001",
                full_name="Alex Morgan",
            )
            session.add(student)
            session.flush()
            session.add_all(
                [
                    User(
                        username="faculty.demo",
                        password_hash=generate_password_hash("Demo123!"),
                        role="faculty",
                    ),
                    User(
                        username="sd.1",
                        password_hash=generate_password_hash("Demo123!"),
                        role="student",
                        student_id=student.id,
                    ),
                ]
            )
            session.commit()

        response = app.test_client().get("/login")

        assert response.status_code == 200
        assert b"Choose a faculty or student account" in response.data
        assert b"Alex Morgan" in response.data
        assert b"faculty.demo" in response.data
        assert b"sd.1" in response.data
        assert b"Demo123!" in response.data
        assert b'aria-label="Show password"' in response.data
        assert b"passwordInput.type = isVisible ?" in response.data
        assert b'getElementById("loginForm").requestSubmit()' in response.data
    finally:
        test_engine.dispose()

    
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


def test_csrf_protect_rejects_missing_and_invalid_tokens():
    app, test_engine = create_test_app()
    app.config["WTF_CSRF_ENABLED"] = True

    try:
        client = app.test_client()
        missing_token = client.post(
            "/login",
            data={
                "username": "faculty.test",
                "password": "TestFaculty@2026",
            },
        )
        invalid_token = client.post(
            "/login",
            data={
                "username": "faculty.test",
                "password": "TestFaculty@2026",
                "csrf_token": "not-a-valid-token",
            },
        )

        assert missing_token.status_code == 400
        assert invalid_token.status_code == 400

        import re

        login_page = client.get("/login")
        match = re.search(
            rb'name="csrf_token"\s+value="([^"]+)"',
            login_page.data,
        )
        assert match is not None
        valid_token = match.group(1).decode()
        accepted_token = client.post(
            "/login",
            data={
                "username": "faculty.test",
                "password": "TestFaculty@2026",
                "csrf_token": valid_token,
            },
        )
        assert accepted_token.status_code == 302
    finally:
        test_engine.dispose()


def test_attendance_can_edit_existing_session_and_record_another_topic():
    app, test_engine = create_test_app()

    try:
        with sessionmaker(bind=test_engine)() as session:
            faculty = session.scalar(
                select(User).where(User.username == "faculty.test")
            )
            student = Student(
                student_code="ATT001",
                full_name="Attendance Test Student",
            )
            course = Course(
                course_code="ATT101",
                title="Attendance Test Course",
            )
            session.add_all([student, course])
            session.flush()
            session.add_all([
                StudentCourse(student_id=student.id, course_id=course.id),
                FacultyCourse(faculty_id=faculty.id, course_id=course.id),
            ])
            session.commit()
            course_id = course.id
            student_id = student.id

        client = app.test_client()
        login_as_faculty(client)
        post_data = {
            "session_date": "2026-10-30",
            "topic": "Database design",
            f"status_{student_id}": "present",
        }

        first = client.post(f"/attendance/course/{course_id}", data=post_data)
        with sessionmaker(bind=test_engine)() as session:
            recorded_session_id = session.scalar(
                select(AttendanceSession.id).where(
                    AttendanceSession.course_id == course_id
                )
            )
        update = client.post(
            f"/attendance/course/{course_id}",
            data={**post_data, f"status_{student_id}": "absent"},
        )
        edit_page = client.get(
            f"/attendance/course/{course_id}?session_id={recorded_session_id}"
        )
        another_topic = client.post(
            f"/attendance/course/{course_id}",
            data={**post_data, "topic": "Transactions"},
        )

        assert first.status_code == 302
        assert update.status_code == 302
        assert edit_page.status_code == 200
        assert b"Edit Attendance" in edit_page.data
        assert b'value="Database design"' in edit_page.data
        assert b'value="absent" selected' in edit_page.data
        assert another_topic.status_code == 302

        sessions_page = client.get(
            f"/attendance/course/{course_id}/sessions"
        )
        assert sessions_page.status_code == 200
        assert b"Database design" in sessions_page.data
        assert b"Transactions" in sessions_page.data

        with sessionmaker(bind=test_engine)() as session:
            sessions = session.scalars(
                select(AttendanceSession).where(
                    AttendanceSession.course_id == course_id
                )
            ).all()
            assert len(sessions) == 2
            attendance_by_topic = {
                item.topic: item for item in sessions
            }
            original_entry = session.scalar(
                select(AttendanceEntry).where(
                    AttendanceEntry.session_id
                    == attendance_by_topic["Database design"].id,
                    AttendanceEntry.student_id == student_id,
                )
            )
            assert original_entry.status == "absent"
            assert session.scalar(
                select(AttendanceEntry.id).where(
                    AttendanceEntry.session_id
                    == attendance_by_topic["Transactions"].id
                )
            ) is not None
    finally:
        test_engine.dispose()


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
    assert response.json["database"] == "available"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_production_configuration_marks_auth_cookies_secure(monkeypatch):
    monkeypatch.setenv("EDUPULSE_ENV", "production")
    app = create_app(
        {
            "TESTING": True,
            "INITIALIZE_DATABASE": False,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret",
        }
    )

    assert app.config["SESSION_COOKIE_SECURE"] is True
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert "max-age=31536000" in response.headers["Strict-Transport-Security"]


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


def test_faculty_can_view_published_marks_but_cannot_change_them():
    app, test_engine = create_test_app()

    try:
        ids = create_assessment_fixture(test_engine)
        with sessionmaker(bind=test_engine)() as session:
            faculty_id = session.scalar(
                select(User.id).where(User.username == "faculty.test")
            )
            assessment = Assessment(
                course_id=ids["course_id"],
                faculty_id=faculty_id,
                title="Published marks view",
                max_marks=30,
                assessment_date=date(2026, 10, 27),
                published=True,
            )
            session.add(assessment)
            session.flush()
            session.add_all([
                AssessmentMark(
                    assessment_id=assessment.id,
                    student_id=ids["student_one_id"],
                    marks=24,
                ),
                AssessmentMark(
                    assessment_id=assessment.id,
                    student_id=ids["student_two_id"],
                    marks=18,
                ),
            ])
            session.commit()
            assessment_id = assessment.id

        client = app.test_client()
        login_as_faculty(client)

        page = client.get(f"/assessments/{assessment_id}/marks")
        assert page.status_code == 200
        assert b"Published results are shown below" in page.data
        assert b"Assessment Student One" in page.data
        assert re.search(rb"<td>\s*24(?:\.0)?\s*</td>", page.data)
        assert b"Save marks" not in page.data

        update = client.post(
            f"/assessments/{assessment_id}/marks",
            data={
                f"marks_{ids['student_one_id']}": "29",
                f"marks_{ids['student_two_id']}": "18",
            },
            follow_redirects=True,
        )
        assert update.status_code == 200
        assert b"Published results are locked" in update.data
        with sessionmaker(bind=test_engine)() as session:
            saved = session.scalar(
                select(AssessmentMark).where(
                    AssessmentMark.assessment_id == assessment_id,
                    AssessmentMark.student_id == ids["student_one_id"],
                )
            )
            assert saved.marks == 24
    finally:
        test_engine.dispose()


def test_student_and_faculty_dashboards_render_attendance_and_mark_bars():
    app, test_engine = create_test_app()

    try:
        ids = create_assessment_fixture(test_engine)
        with sessionmaker(bind=test_engine)() as session:
            faculty = session.scalar(
                select(User).where(User.username == "faculty.test")
            )
            student = session.get(Student, ids["student_one_id"])
            session.add(
                User(
                    username="chart.student",
                    password_hash=generate_password_hash("StudentTest@2026"),
                    role="student",
                    student_id=student.id,
                )
            )
            attendance_session = AttendanceSession(
                course_id=ids["course_id"],
                faculty_id=faculty.id,
                session_date=date(2026, 10, 25),
                topic="Dashboard chart session",
            )
            assessment = Assessment(
                course_id=ids["course_id"],
                faculty_id=faculty.id,
                title="Dashboard chart assessment",
                max_marks=30,
                assessment_date=date(2026, 10, 26),
                published=True,
            )
            session.add_all([attendance_session, assessment])
            session.flush()
            session.add_all([
                AttendanceEntry(
                    session_id=attendance_session.id,
                    student_id=ids["student_one_id"],
                    status="present",
                ),
                AttendanceEntry(
                    session_id=attendance_session.id,
                    student_id=ids["student_two_id"],
                    status="absent",
                ),
                AssessmentMark(
                    assessment_id=assessment.id,
                    student_id=ids["student_one_id"],
                    marks=24,
                ),
                AssessmentMark(
                    assessment_id=assessment.id,
                    student_id=ids["student_two_id"],
                    marks=18,
                ),
            ])
            session.commit()

        faculty_client = app.test_client()
        login_as_faculty(faculty_client)
        faculty_dashboard = faculty_client.get("/")
        assert b"Attendance by subject" in faculty_dashboard.data
        assert b"Assessment average by subject" in faculty_dashboard.data
        assert b"70.0%" in faculty_dashboard.data
        assert b"Students" in faculty_dashboard.data
        assert b"Add Student" not in faculty_dashboard.data
        assert b"Add Course" not in faculty_dashboard.data

        student_client = app.test_client()
        student_login = student_client.post(
            "/login",
            data={
                "username": "chart.student",
                "password": "StudentTest@2026",
            },
            follow_redirects=True,
        )
        assert student_login.status_code == 200
        assert b"Attendance by subject" in student_login.data
        assert b"Assessment scores" in student_login.data
        assert b"100.0%" in student_login.data
        assert b"24.0 / 30.0 marks" in student_login.data
        assert f"/student/courses/{ids['course_id']}".encode() in student_login.data
        assert b"View subject details" in student_login.data
    finally:
        test_engine.dispose()


def test_student_subject_detail_shows_dates_attendance_and_published_marks():
    app, test_engine = create_test_app()

    try:
        ids = create_assessment_fixture(test_engine)
        with sessionmaker(bind=test_engine)() as session:
            faculty_id = session.scalar(
                select(User.id).where(User.username == "faculty.test")
            )
            student = session.get(Student, ids["student_one_id"])
            session.add(
                User(
                    username="detail.student",
                    password_hash=generate_password_hash("StudentTest@2026"),
                    role="student",
                    student_id=student.id,
                )
            )
            class_session = AttendanceSession(
                course_id=ids["course_id"],
                faculty_id=faculty_id,
                session_date=date(2026, 10, 28),
                topic="Functions and scope",
            )
            published = Assessment(
                course_id=ids["course_id"],
                faculty_id=faculty_id,
                title="Midterm assessment",
                max_marks=40,
                assessment_date=date(2026, 10, 29),
                published=True,
            )
            draft = Assessment(
                course_id=ids["course_id"],
                faculty_id=faculty_id,
                title="Unpublished practice",
                max_marks=20,
                assessment_date=date(2026, 10, 30),
                published=False,
            )
            session.add_all([class_session, published, draft])
            session.flush()
            session.add_all([
                AttendanceEntry(
                    session_id=class_session.id,
                    student_id=student.id,
                    status="late",
                ),
                AssessmentMark(
                    assessment_id=published.id,
                    student_id=student.id,
                    marks=32,
                ),
                AssessmentMark(
                    assessment_id=draft.id,
                    student_id=student.id,
                    marks=19,
                ),
            ])
            session.commit()

        client = app.test_client()
        client.post(
            "/login",
            data={
                "username": "detail.student",
                "password": "StudentTest@2026",
            },
        )
        page = client.get(f"/student/courses/{ids['course_id']}")
        assert page.status_code == 200
        assert b"Attendance by date" in page.data
        assert b"28 Oct 2026" in page.data
        assert b"Functions and scope" in page.data
        assert b"Late" in page.data
        assert b"Midterm assessment" in page.data
        assert b"32" in page.data
        assert b"Unpublished practice" not in page.data
        assert client.get("/student/courses/9999").status_code == 404
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


def test_academic_support_tracks_follow_up_to_completion():
    app, test_engine = create_test_app()

    try:
        ids = create_analytics_fixture(test_engine)
        with sessionmaker(bind=test_engine)() as session:
            enrollment = session.scalar(
                select(StudentCourse).where(
                    StudentCourse.student_id == ids["student_id"],
                    StudentCourse.course_id == ids["course_id"],
                )
            )

            attendance_session = AttendanceSession(
                course_id=ids["course_id"],
                faculty_id=ids["faculty_id"],
                session_date=date(2026, 10, 1),
                topic="Support test session",
            )
            first_assessment = Assessment(
                course_id=ids["course_id"],
                faculty_id=ids["faculty_id"],
                title="Support test 1",
                max_marks=100,
                assessment_date=date(2026, 10, 2),
                published=True,
            )
            second_assessment = Assessment(
                course_id=ids["course_id"],
                faculty_id=ids["faculty_id"],
                title="Support test 2",
                max_marks=100,
                assessment_date=date(2026, 10, 3),
                published=True,
            )
            session.add_all([
                attendance_session,
                first_assessment,
                second_assessment,
            ])
            session.flush()
            session.add_all([
                AttendanceEntry(
                    session_id=attendance_session.id,
                    student_id=ids["student_id"],
                    status="absent",
                ),
                AssessmentMark(
                    assessment_id=first_assessment.id,
                    student_id=ids["student_id"],
                    marks=82,
                ),
                AssessmentMark(
                    assessment_id=second_assessment.id,
                    student_id=ids["student_id"],
                    marks=54,
                ),
                AcademicRecord(
                    student_course_id=enrollment.id,
                    attendance_percentage=0,
                    assessment_scores=[82, 54],
                    completed_assignments=4,
                    total_assignments=10,
                ),
            ])
            session.commit()
            enrollment_id = enrollment.id

        client = app.test_client()
        login_as_faculty(client)
        report = client.get(f"/academic-support/{ids['course_id']}")

        assert report.status_code == 200
        assert b"Review recent assessments with the student" in report.data
        assert b"Record a support follow-up" in report.data
        assert b"&#39;recommendation&#39;" not in report.data

        created = client.post(
            f"/academic-support/{ids['course_id']}/follow-ups",
            data={
                "enrollment_id": str(enrollment_id),
                "finding_rule": "assessment_trend",
                "action_text": "Review recent assessments with the student.",
                "notes": "Arrange a short support check-in.",
                "due_date": "2026-11-07",
            },
            follow_redirects=True,
        )
        assert created.status_code == 200
        assert b"Follow-up history" in created.data
        assert b"Arrange a short support check-in." in created.data

        with sessionmaker(bind=test_engine)() as session:
            follow_up = session.scalar(select(SupportFollowUp))
            follow_up_id = follow_up.id
            assert follow_up.status == "open"

        updated = client.post(
            f"/academic-support/follow-ups/{follow_up_id}/status",
            data={"status": "completed"},
            follow_redirects=True,
        )
        assert updated.status_code == 200
        assert b"Completed" in updated.data

        with sessionmaker(bind=test_engine)() as session:
            follow_up = session.get(SupportFollowUp, follow_up_id)
            assert follow_up.status == "completed"
    finally:
        test_engine.dispose()


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
        assert b"Assessment trend" in response.data
        assert b'id="assessmentTrend"' in response.data
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
