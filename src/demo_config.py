"""Credentials and username conventions for the explicitly seeded demo cohort."""

DEMO_PASSWORD = "Demo123!"
STUDENT_USERNAME_PREFIX = "sd."
STUDENT_USERNAME = "sd.1"
FACULTY_USERNAME = "faculty.demo"


def student_demo_username(index):
    """Return the short username assigned to a demo student."""
    return f"{STUDENT_USERNAME_PREFIX}{index + 1}"
