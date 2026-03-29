import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


logger = logging.getLogger("brainapi.db")


class Base(DeclarativeBase):
    pass



engine = create_engine(settings.normalized_database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from .models import APIKey, EmailEvent, PasswordResetToken, ProductReview, SignupLead, UsageEvent, UserAccount  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_schema_updates()


def _ensure_schema_updates() -> None:
    """
    Self-healing database utility. 
    Checks if new columns exist and adds them if they don't.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    dialect = engine.dialect.name
    statements: list[str] = []

    # 1. Existing check for api_keys
    if "api_keys" in tables:
        api_key_cols = {col["name"] for col in inspector.get_columns("api_keys")}
        if "is_paid" not in api_key_cols:
            statements.append(f"ALTER TABLE api_keys ADD COLUMN is_paid {'BOOLEAN NOT NULL DEFAULT FALSE' if dialect == 'postgresql' else 'BOOLEAN NOT NULL DEFAULT 0'}")
        if "trial_ends_at" not in api_key_cols:
            statements.append(f"ALTER TABLE api_keys ADD COLUMN trial_ends_at {'TIMESTAMPTZ NULL' if dialect == 'postgresql' else 'DATETIME NULL'}")

    # 2. Check for email_events (Fixes your current deployment errors)
    if "email_events" in tables:
        email_cols = {col["name"] for col in inspector.get_columns("email_events")}
        
        if "html_body" not in email_cols:
            statements.append("ALTER TABLE email_events ADD COLUMN html_body TEXT NULL")
            
        if "retry_count" not in email_cols:
            # Handles different integer syntax for Postgres vs SQLite
            col_type = 'INTEGER DEFAULT 0'
            statements.append(f"ALTER TABLE email_events ADD COLUMN retry_count {col_type}")

    if not statements:
        return

    with engine.connect() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                conn.commit()
                logger.info(f"Executed schema update: {stmt}")
            except Exception as e:
                logger.error(f"Failed to execute {stmt}: {e}")