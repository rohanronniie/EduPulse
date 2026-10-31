
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class User(Base):
    """Login account for a student or faculty member."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('student', 'faculty')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class FacultyCourse(Base):
    """Courses a faculty account is authorized to manage."""

    __tablename__ = "faculty_courses"
    __table_args__ = (
        UniqueConstraint("faculty_id", "course_id", name="uq_faculty_course"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )


class AttendanceSession(Base):
    """A single class session for a course."""

    __tablename__ = "attendance_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    session_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    topic: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AttendanceEntry(Base):
    """Attendance status for one student in one class session."""

    __tablename__ = "attendance_entries"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_student"),
        CheckConstraint(
            "status IN ('present', 'absent', 'late')",
            name="ck_attendance_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class SupportFollowUp(Base):
    """Record a faculty support action and its follow-through state."""

    __tablename__ = "support_follow_ups"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'completed')",
            name="ck_support_follow_up_status",
        ),
        CheckConstraint(
            "finding_rule IN ('attendance', 'assessment_trend', "
            "'assignment_completion', 'general')",
            name="ck_support_follow_up_rule",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_course_id: Mapped[int] = mapped_column(
        ForeignKey("student_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    finding_rule: Mapped[str] = mapped_column(String(40), nullable=False)
    action_text: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Assessment(Base):
    """An assessment belonging to a course."""

    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("max_marks > 0", name="ck_assessment_max_marks_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    max_marks: Mapped[float] = mapped_column(Float, nullable=False)
    assessment_date: Mapped[date] = mapped_column(
        Date, default=date.today, nullable=False
    )
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AssessmentMark(Base):
    """A student's mark for one assessment."""

    __tablename__ = "assessment_marks"
    __table_args__ = (
        UniqueConstraint("assessment_id", "student_id", name="uq_assessment_student"),
        CheckConstraint("marks >= 0", name="ck_assessment_marks_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    marks: Mapped[float] = mapped_column(Float, nullable=False)
