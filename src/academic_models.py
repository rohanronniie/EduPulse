
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class AcademicRecord(Base):
    """Store academic inputs for one student enrolled in one course."""

    __tablename__ = "academic_records"

    __table_args__ = (
        UniqueConstraint(
            "student_course_id",
            name="uq_academic_record_student_course",
        ),
        CheckConstraint(
            "attendance_percentage >= 0 AND attendance_percentage <= 100",
            name="ck_academic_attendance_range",
        ),
        CheckConstraint(
            "completed_assignments >= 0",
            name="ck_academic_completed_assignments_nonnegative",
        ),
        CheckConstraint(
            "total_assignments >= completed_assignments",
            name="ck_academic_assignment_counts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    student_course_id: Mapped[int] = mapped_column(
        ForeignKey("student_courses.id", ondelete="CASCADE"),
        nullable=False,
    )

    attendance_percentage: Mapped[float] = mapped_column(nullable=False)
    assessment_scores: Mapped[list] = mapped_column(JSON, nullable=False)
    completed_assignments: Mapped[int] = mapped_column(nullable=False)
    total_assignments: Mapped[int] = mapped_column(nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    enrollment: Mapped["StudentCourse"] = relationship()
