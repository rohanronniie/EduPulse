
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src.database import Base


class Student(Base):
    """Represent a student registered in EduPulse."""

    __tablename__ = "students"

    __table_args__ = (
        CheckConstraint(
            "length(trim(student_code)) > 0",
            name="ck_students_code_not_blank",
        ),
        CheckConstraint(
            "length(trim(full_name)) > 0",
            name="ck_students_name_not_blank",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    student_code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    enrollments: Mapped[list["StudentCourse"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )

    @validates("student_code", "full_name")
    def validate_non_blank(self, key, value):
        """Reject missing, non-string, or blank text values."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string.")

        return value.strip()


class Course(Base):
    """Represent a course offered in EduPulse."""

    __tablename__ = "courses"

    __table_args__ = (
        CheckConstraint(
            "length(trim(course_code)) > 0",
            name="ck_courses_code_not_blank",
        ),
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_courses_title_not_blank",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    course_code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    enrollments: Mapped[list["StudentCourse"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )

    @validates("course_code", "title")
    def validate_non_blank(self, key, value):
        """Reject missing, non-string, or blank text values."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string.")

        return value.strip()


class StudentCourse(Base):
    """Represent a student's enrollment in a course."""

    __tablename__ = "student_courses"

    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "course_id",
            name="uq_student_course_enrollment",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
    )

    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    student: Mapped["Student"] = relationship(
        back_populates="enrollments",
    )

    course: Mapped["Course"] = relationship(
        back_populates="enrollments",
    )
