from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .db import SessionLocal
from .models import UsageEvent
MAX_REQUESTS_PER_DAY = 1000

def enforce_daily_limit(api_key_id: str | None, api_key_label: str) -> None:

    today = datetime.now(timezone.utc) - timedelta(hours=24)

    with SessionLocal() as db:

        if api_key_id:
            count = db.scalar(
                select(func.count(UsageEvent.id))
                .where(
                    UsageEvent.api_key_id == api_key_id,
                    UsageEvent.created_at >= today,
                )
            )
        else:
            count = db.scalar(
                select(func.count(UsageEvent.id))
                .where(
                    UsageEvent.api_key_label == api_key_label,
                    UsageEvent.created_at >= today,
                )
            )

        count = count or 0

        if count >= MAX_REQUESTS_PER_DAY:
            raise Exception("Daily API request limit exceeded")
def record_usage_event(
    api_key_id: str | None,
    api_key_label: str,
    endpoint: str,
    method: str,
    status_code: int,
    duration_ms: int,
) -> None:

    enforce_daily_limit(api_key_id, api_key_label)

    with SessionLocal() as db:
        event = UsageEvent(
            api_key_id=api_key_id,
            api_key_label=api_key_label,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        db.add(event)
        db.commit()


def usage_summary(hours: int = 24) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    with SessionLocal() as db:
        total_requests = db.scalar(
            select(func.count(UsageEvent.id)).where(UsageEvent.created_at >= since)
        ) or 0

        by_endpoint_rows = db.execute(
            select(UsageEvent.endpoint, func.count(UsageEvent.id))
            .where(UsageEvent.created_at >= since)
            .group_by(UsageEvent.endpoint)
            .order_by(func.count(UsageEvent.id).desc())
        ).all()

        by_key_rows = db.execute(
            select(UsageEvent.api_key_label, func.count(UsageEvent.id))
            .where(UsageEvent.created_at >= since)
            .group_by(UsageEvent.api_key_label)
            .order_by(func.count(UsageEvent.id).desc())
        ).all()

    return {
        "window_hours": hours,
        "total_requests": int(total_requests),
        "by_endpoint": [{"endpoint": endpoint, "count": int(count)} for endpoint, count in by_endpoint_rows],
        "by_key": [{"api_key": api_key, "count": int(count)} for api_key, count in by_key_rows],
    }


def per_key_usage_summary(key_id: str | None, key_label: str, hours: int = 24) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    with SessionLocal() as db:
        if key_id is not None:
            base_filter = (UsageEvent.api_key_id == key_id) & (UsageEvent.created_at >= since)
        else:
            base_filter = (UsageEvent.api_key_label == key_label) & (UsageEvent.created_at >= since)

        total = db.scalar(select(func.count(UsageEvent.id)).where(base_filter)) or 0

        by_endpoint_rows = db.execute(
            select(UsageEvent.endpoint, func.count(UsageEvent.id))
            .where(base_filter)
            .group_by(UsageEvent.endpoint)
            .order_by(func.count(UsageEvent.id).desc())
            .limit(10)
        ).all()

        by_status_rows = db.execute(
            select(UsageEvent.status_code, func.count(UsageEvent.id))
            .where(base_filter)
            .group_by(UsageEvent.status_code)
            .order_by(func.count(UsageEvent.id).desc())
        ).all()

    return {
        "window_hours": hours,
        "total_requests": int(total),
        "by_endpoint": [{"endpoint": ep, "count": int(c)} for ep, c in by_endpoint_rows],
        "by_status": [{"status_code": int(sc), "count": int(c)} for sc, c in by_status_rows],
    }
