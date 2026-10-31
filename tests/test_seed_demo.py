import re

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from werkzeug.security import check_password_hash

import seed_demo
from src import create_app
from src.academic_models import AcademicRecord
from src.database import Base
from src.models import Course, Student
from src.portal_models import (
    Assessment,
    AssessmentMark,
    AttendanceEntry,
    AttendanceSession,
    SupportFollowUp,
    User,
)


def test_demo_seed_builds_a_repeatable_cohort(monkeypatch):
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
    monkeypatch.setattr(seed_demo, "SessionLocal", test_session_factory)
    monkeypatch.setattr(
        seed_demo,
        "initialize_database",
        lambda: Base.metadata.create_all(bind=test_engine),
    )

    try:
        seed_demo.seed_demo_data()
        seed_demo.seed_demo_data()

        with test_session_factory() as db:
            assert db.scalar(
                select(func.count(Student.id)).where(
                    Student.student_code.like("DEMO%")
                )
            ) == 8
            assert db.scalar(
                select(func.count(Course.id)).where(
                    Course.course_code.in_(
                        ["DEMO101", "DATA201", "UXD120", "PMGT210"]
                    )
                )
            ) == 4
            assert db.scalar(
                select(func.count(AttendanceSession.id)).where(
                    AttendanceSession.topic.like("Week %")
                )
            ) == 40
            assert db.scalar(select(func.count(AttendanceEntry.id))) == 320
            assert db.scalar(select(func.count(Assessment.id))) == 12
            assert db.scalar(select(func.count(AssessmentMark.id))) == 96
            assert db.scalar(select(func.count(AcademicRecord.id))) == 32
            assert db.scalar(select(func.count(SupportFollowUp.id))) == 8
            assert db.scalar(
                select(User.id).where(User.username == "sd.1")
            ) is not None
            demo_students = db.scalars(
                select(User).where(
                    User.username.like("sd.%"),
                    User.role == "student",
                )
            ).all()
            assert len(demo_students) == 8
            assert len({account.student_id for account in demo_students}) == 8
            assert all(
                check_password_hash(account.password_hash, "Demo123!")
                for account in demo_students
            )
            assert db.scalar(
                select(User.id).where(User.username == "faculty.demo")
            ) is not None
            faculty = db.scalar(
                select(User).where(User.username == "faculty.demo")
            )
            assert check_password_hash(faculty.password_hash, "Demo123!")

        app = create_app(
            {
                "TESTING": True,
                "INITIALIZE_DATABASE": False,
                "SESSION_FACTORY": test_session_factory,
                "SECRET_KEY": "demo-login-test-secret",
            }
        )
        for student_index in range(8):
            username = seed_demo.student_demo_username(student_index)
            expected_name = seed_demo.STUDENTS[student_index][1]
            client = app.test_client()
            login_page = client.get("/login")
            token = re.search(
                rb'name="csrf_token"\s+value="([^"]+)"',
                login_page.data,
            ).group(1).decode()
            response = client.post(
                "/login",
                data={
                    "username": username,
                    "password": "Demo123!",
                    "csrf_token": token,
                },
            )
            assert response.status_code == 302
            dashboard = client.get("/")
            assert dashboard.status_code == 200
            assert expected_name.encode() in dashboard.data

        faculty_client = app.test_client()
        faculty_login_page = faculty_client.get("/login")
        faculty_token = re.search(
            rb'name="csrf_token"\s+value="([^"]+)"',
            faculty_login_page.data,
        ).group(1).decode()
        faculty_response = faculty_client.post(
            "/login",
            data={
                "username": "faculty.demo",
                "password": "Demo123!",
                "csrf_token": faculty_token,
            },
        )
        assert faculty_response.status_code == 302
        faculty_dashboard = faculty_client.get("/")
        assert faculty_dashboard.status_code == 200
        assert b"Data Analytics and Visualization" in faculty_dashboard.data
    finally:
        test_engine.dispose()
