from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal
from .models import APIKey, EmailEvent, SignupLead, UsageEvent


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def support_email_value() -> str:
    for value in (
        settings.support_email,
        settings.email_reply_to,
        settings.email_from_address,
    ):
        cleaned = (value or "").strip()
        if cleaned:
            return cleaned
    return "brainapisupport@gmail.com"


def founder_name_value() -> str:
    return (settings.founder_name or "").strip() or "BrainAPI founder"


def public_status_payload() -> dict:
    is_sqlite_database = settings.database_url.strip().lower().startswith("sqlite")
    return {
        "success": True,
        "status": "operational" if settings.provider_ready else "degraded",
        "provider": settings.provider_name,
        "provider_ready": settings.provider_ready,
        "environment": settings.environment,
        "database_persistent": not is_sqlite_database,
        "support_email": support_email_value(),
        "founder_name": founder_name_value(),
        "docs_url": "/ui/quickstart.html",
        "dashboard_url": "/ui/dashboard.html#overview",
        "signup_url": "/ui/signup.html",
        "health_url": "/health",
        "metrics_url": "/api/v1/metrics",
        "status_page_url": "/status",
    }


def launch_metrics_summary(days: int = 30) -> dict:
    since = _utc_now() - timedelta(days=days)

    with SessionLocal() as db:
        signups = db.scalar(
            select(func.count(SignupLead.id)).where(SignupLead.created_at >= since)
        ) or 0

        paid_customers = db.scalar(
            select(func.count(func.distinct(SignupLead.api_key_id)))
            .select_from(SignupLead)
            .join(APIKey, SignupLead.api_key_id == APIKey.id)
            .where(
                SignupLead.created_at >= since,
                APIKey.is_paid.is_(True),
            )
        ) or 0

        api_calls = db.scalar(
            select(func.count(UsageEvent.id)).where(UsageEvent.created_at >= since)
        ) or 0

        failed_emails = db.scalar(
            select(func.count(EmailEvent.id))
            .where(
                EmailEvent.created_at >= since,
                EmailEvent.status == "failed",
            )
        ) or 0

        sent_emails = db.scalar(
            select(func.count(EmailEvent.id))
            .where(
                EmailEvent.created_at >= since,
                EmailEvent.status == "sent",
            )
        ) or 0

        by_source_rows = db.execute(
            select(SignupLead.source, func.count(SignupLead.id))
            .where(SignupLead.created_at >= since)
            .group_by(SignupLead.source)
            .order_by(func.count(SignupLead.id).desc())
        ).all()

    conversion_rate = round((paid_customers / signups) * 100, 2) if signups else 0.0
    total_email_attempts = failed_emails + sent_emails
    email_failure_rate = round((failed_emails / total_email_attempts) * 100, 2) if total_email_attempts else 0.0

    return {
        "window_days": days,
        "signups": int(signups),
        "paid_customers": int(paid_customers),
        "conversion_rate": conversion_rate,
        "api_calls": int(api_calls),
        "failed_emails": int(failed_emails),
        "sent_emails": int(sent_emails),
        "email_failure_rate": email_failure_rate,
        "top_signup_sources": [
            {"source": source or "unknown", "count": int(count)}
            for source, count in by_source_rows
        ],
    }
