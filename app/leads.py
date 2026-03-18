from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select

from .auth import create_db_api_key
from .db import SessionLocal
from .models import SignupLead


class SignupError(Exception):
    pass


def create_trial_signup(
    *,
    name: str,
    email: str,
    company: str | None,
    use_case: str | None,
    source: str | None,
    trial_days: int,
    rate_limit_per_minute: int | None,
) -> dict:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise SignupError("Email is required")

    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(hours=24)

    with SessionLocal() as db:
        recent = db.scalars(
            select(SignupLead)
            .where(SignupLead.email == normalized_email)
            .where(SignupLead.created_at >= recent_cutoff)
            .order_by(desc(SignupLead.created_at))
            .limit(1)
        ).first()
        if recent is not None:
            raise SignupError("A trial signup was already created for this email in the last 24 hours")

    created = create_db_api_key(
        name=f"trial:{name.strip()[:40] or 'user'}",
        rate_limit_per_minute=rate_limit_per_minute,
        trial_days=trial_days,
        is_paid=False,
    )

    with SessionLocal() as db:
        lead = SignupLead(
            name=name.strip()[:120],
            email=normalized_email[:190],
            company=(company or "").strip()[:160] or None,
            use_case=(use_case or "").strip()[:500] or None,
            source=(source or "").strip()[:80] or None,
            consent=True,
            api_key_id=created["id"],
            created_at=now,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)

    return {
        "lead_id": lead.id,
        "name": lead.name,
        "email": lead.email,
        "api_key_id": created["id"],
        "api_key": created["api_key"],
        "key_prefix": created["key_prefix"],
        "trial_ends_at": created["trial_ends_at"],
        "is_paid": created["is_paid"],
        "rate_limit_per_minute": created["rate_limit_per_minute"],
    }
