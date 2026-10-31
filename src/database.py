
from pathlib import Path
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Store the database in the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "edupulse.db"

def resolve_database_url(environment=None):
    """Resolve a configured database URL, defaulting on missing or blank values."""
    environment = os.environ if environment is None else environment
    database_url = (environment.get("EDUPULSE_DATABASE_URL") or "").strip()
    if not database_url:
        database_url = f"sqlite:///{DATABASE_PATH.as_posix()}"

    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )
    return database_url


DATABASE_URL = resolve_database_url()

engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite:"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)


if DATABASE_URL.startswith("sqlite:"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        """Enable foreign-key enforcement for SQLite connections."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all EduPulse database models."""

    pass


def initialize_database():
    """Create any database tables not yet present."""
    from src import models
    from src import academic_models
    from src import portal_models

    Base.metadata.create_all(bind=engine)
