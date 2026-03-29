from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Optional
from urllib.parse import quote_plus, urlparse

import requests
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import SessionLocal
from .email_validation import validate_email_address
from .models import EmailEvent, SignupLead

logger = logging.getLogger("brainapi.email")


class EmailDeliveryError(Exception):
    """Raised when the email provider fails to accept a message."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_timezone(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _base_url() -> str:
    base = (settings.public_base_url or "").strip() or "http://localhost:8000"
    return base.rstrip("/")


def _absolute_url(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return f"{_base_url()}{path}"


def _default_from_address() -> str:
    configured = (settings.email_from_address or "").strip()
    if configured:
        return configured

    parsed = urlparse(settings.public_base_url or "")
    hostname = parsed.hostname or "brainapi.site"
    return f"noreply@{hostname}"


def _format_trial_end(value: Optional[datetime]) -> str:
    if not value:
        return "soon"
    aware = _ensure_timezone(value)
    return aware.strftime("%B %d, %Y")


def _format_inr(amount: Optional[float]) -> str:
    if amount is None:
        return "₹0"
    value = float(amount)
    if value.is_integer():
        return f"₹{int(value)}"
    return f"₹{value:.2f}"


def _truncate_required(value: Any, limit: int) -> str:
    text = str(value or "")
    return text[:limit]


def _truncate_optional(value: Optional[Any], limit: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    return text[:limit]


def _build_result(*, success: bool, status: str, message: str, error: Optional[str] = None, event: Optional[EmailEvent] = None) -> dict[str, Any]:
    return {
        "success": bool(success),
        "status": status,
        "message": message,
        "error": error,
        "id": event.id if event is not None else None,
    }


def _validate_recipient(recipient_email: str) -> tuple[Optional[str], Optional[str]]:
    validation = validate_email_address(recipient_email, set(settings.blocked_email_domains_list))
    if not validation.is_valid:
        return None, validation.error or "Email is invalid."
    return validation.normalized_email, None


def _environment_skip_reason() -> Optional[str]:
    if settings.environment.lower() != "production" and settings.skip_email_in_development:
        return "Email skipped in development mode."
    return None


def _deliver_email(event: EmailEvent) -> dict[str, Any]:
    provider = (settings.email_provider or "smtp").strip().lower()
    if provider == "resend":
        return _send_resend_email(
            recipient_email=event.recipient_email,
            subject=event.subject,
            body_text=event.body_text,
            html_body=event.html_body,
        )

    return _send_smtp_email(
        recipient_email=event.recipient_email,
        subject=event.subject,
        body_text=event.body_text,
        html_body=event.html_body,
    )


def _send_smtp_email(*, recipient_email: str, subject: str, body_text: str, html_body: Optional[str]) -> dict[str, Any]:
    host = (settings.smtp_host or "").strip()
    if not host:
        raise EmailDeliveryError("SMTP host is not configured.")

    message = EmailMessage()
    message["To"] = recipient_email
    message["From"] = formataddr((settings.email_from_name or "BrainAPI", _default_from_address()))
    message["Subject"] = subject

    reply_to = (settings.email_reply_to or "").strip()
    if reply_to:
        message["Reply-To"] = reply_to

    message.set_content(body_text or "")
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as client:
            if settings.smtp_use_tls:
                client.starttls()
            username = (settings.smtp_username or "").strip()
            password = settings.smtp_password or ""
            if username and password:
                client.login(username, password)
            client.send_message(message)
    except Exception as exc:  # pragma: no cover - network failures are logged
        logger.exception("SMTP delivery failed for %s", recipient_email)
        raise EmailDeliveryError(str(exc)) from exc

    return {"status": "sent", "message": "SMTP message dispatched."}


def _send_resend_email(*, recipient_email: str, subject: str, body_text: str, html_body: Optional[str]) -> dict[str, Any]:
    api_key = (settings.resend_api_key or "").strip()
    if not api_key:
        raise EmailDeliveryError("RESEND_API_KEY is not configured.")

    payload = {
        "from": formataddr((settings.email_from_name or "BrainAPI", _default_from_address())),
        "to": [recipient_email],
        "subject": subject,
        "text": body_text or "",
    }
    if html_body:
        payload["html"] = html_body

    response = requests.post(
        "https://api.resend.com/emails",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    if response.status_code >= 400:
        raise EmailDeliveryError(f"Resend API error: {response.status_code} {response.text}")

    return {"status": "sent", "message": "Resend accepted email."}


def queue_email_event(
    *,
    event_type: str,
    recipient_email: str,
    subject: str,
    body_text: str,
    html_body: Optional[str] = None,
    dedupe_key: Optional[str] = None,
    scheduled_for: Optional[datetime] = None,
) -> dict[str, Any]:
    normalized_email, validation_error = _validate_recipient(recipient_email)
    if normalized_email is None:
        return _build_result(success=False, status="skipped", message="Email skipped.", error=validation_error)

    clean_dedupe = (dedupe_key or "").strip() or None
    scheduled_at = _ensure_timezone(scheduled_for)

    event = EmailEvent(
        event_type=_truncate_required(event_type, 80),
        recipient_email=normalized_email[:190],
        subject=_truncate_required(subject, 255),
        body_text=_truncate_required(body_text, 4000),
        html_body=_truncate_optional(html_body, 8000),
        status="scheduled" if scheduled_at and scheduled_at > _now() else "queued",
        dedupe_key=_truncate_optional(clean_dedupe, 255),
        scheduled_for=scheduled_at,
    )

    with SessionLocal() as db:
        db.add(event)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if clean_dedupe:
                existing = db.scalar(
                    select(EmailEvent)
                    .where(EmailEvent.dedupe_key == clean_dedupe)
                    .order_by(desc(EmailEvent.created_at))
                    .limit(1)
                )
                if existing:
                    return _build_result(success=True, status=existing.status, message="Email already queued.", event=existing)
            logger.exception("Failed to queue email event type=%s email=%s", event_type, normalized_email)
            return _build_result(success=False, status="error", message="Failed to queue email event.", error="Duplicate or invalid email event")

        db.refresh(event)
        return _build_result(success=True, status=event.status, message="Email queued.", event=event)


def dispatch_transactional_email(event_id: str) -> dict[str, Any]:
    clean_id = (event_id or "").strip()
    if not clean_id:
        return _build_result(success=False, status="missing", message="Email event not found.", error="event_id is required")

    with SessionLocal() as db:
        event = db.get(EmailEvent, clean_id)
        if event is None:
            return _build_result(success=False, status="missing", message="Email event not found.", error="Email event not found")

        if event.status == "sent":
            return _build_result(success=True, status="sent", message="Email already sent.", event=event)

        if event.status == "skipped":
            return _build_result(success=False, status="skipped", message="Email was skipped.", error=event.error_message, event=event)

        skip_reason = _environment_skip_reason()
        if skip_reason:
            event.status = "skipped"
            event.error_message = skip_reason
            event.sent_at = None
            db.commit()
            db.refresh(event)
            return _build_result(success=False, status="skipped", message=skip_reason, event=event)

        try:
            delivery = _deliver_email(event)
        except EmailDeliveryError as exc:
            event.status = "failed"
            event.error_message = str(exc)
            event.retry_count = (event.retry_count or 0) + 1
            db.commit()
            db.refresh(event)
            return _build_result(success=False, status="failed", message="Email delivery failed.", error=str(exc), event=event)

        event.status = "sent"
        event.sent_at = _now()
        event.error_message = None
        db.commit()
        db.refresh(event)

        delivery_message = delivery.get("message") if isinstance(delivery, dict) else None
        return _build_result(success=True, status="sent", message=delivery_message or "Email sent.", event=event)


def send_custom_email(*, recipient_email: str, subject: str, body_text: str, html_body: Optional[str] = None) -> dict[str, Any]:
    queued = queue_email_event(
        event_type="custom",
        recipient_email=recipient_email,
        subject=subject,
        body_text=body_text,
        html_body=html_body,
    )
    if not queued.get("success"):
        return queued

    return dispatch_transactional_email(queued["id"])


def send_email(to_email: str, subject: str, html_content: str, body_text: Optional[str] = None) -> dict[str, Any]:
    return send_custom_email(
        recipient_email=to_email,
        subject=subject,
        body_text=body_text or "",
        html_body=html_content,
    )


def email_delivery_health() -> dict[str, Any]:
    provider = (settings.email_provider or "smtp").strip().lower()
    environment = settings.environment
    skip_in_development = bool(settings.skip_email_in_development)

    if provider == "resend":
        configured = bool((settings.resend_api_key or "").strip())
    else:
        configured = bool((settings.smtp_host or "").strip())

    delivery_enabled = configured and (environment.lower() == "production" or not skip_in_development)

    return {
        "status": "ok" if configured else "disabled",
        "provider": provider,
        "environment": environment,
        "configured": configured,
        "delivery_enabled": delivery_enabled,
        "skip_in_development": skip_in_development,
        "from_address": _default_from_address(),
    }


def get_lead_contact_for_api_key(api_key_id: Optional[str]) -> Optional[dict[str, Any]]:
    clean_id = (api_key_id or "").strip()
    if not clean_id:
        return None

    with SessionLocal() as db:
        lead = db.scalar(
            select(SignupLead)
            .where(SignupLead.api_key_id == clean_id)
            .order_by(desc(SignupLead.created_at))
            .limit(1)
        )
        if lead is None:
            return None
        return {"id": lead.id, "name": lead.name, "email": lead.email}


def queue_password_reset_email(*, email: str, reset_token: str) -> dict[str, Any]:
    reset_link = _absolute_url(f"/ui/forgot-password.html?token={quote_plus(reset_token)}")
    subject = "BrainAPI - Reset your password"
    body_text = (
        "Hi,\n\n"
        "We received a request to reset your BrainAPI password.\n"
        f"Reset link: {reset_link}\n\n"
        "If you did not request this, you can ignore this email.\n\n"
        f"Thanks,\n{settings.founder_name}"
    )
    html_body = (
        "<p>We received a request to reset your BrainAPI password.</p>"
        f"<p><a href=\"{reset_link}\">Reset your password</a></p>"
        "<p>If you did not request this change, please ignore this email.</p>"
        f"<p>Thanks,<br>{settings.founder_name}</p>"
    )
    return queue_email_event(
        event_type="password_reset",
        recipient_email=email,
        subject=subject,
        body_text=body_text,
        html_body=html_body,
        dedupe_key=f"password_reset:{email}:{reset_token}",
    )


def queue_welcome_email(*, name: str, email: str, api_key: str, trial_ends_at: Optional[datetime]) -> dict[str, Any]:
    subject = "Welcome to BrainAPI"
    body_text = (
        f"Hi {name or 'there'},\n\n"
        "Welcome to BrainAPI! Your API key is ready to use.\n"
        f"API key: {api_key}\n"
        f"Trial ends: {_format_trial_end(trial_ends_at)}\n\n"
        f"Dashboard: {_absolute_url('/ui/dashboard.html')}\n"
        f"Quickstart: {_absolute_url('/ui/onboarding.html')}\n\n"
        f"Cheers,\n{settings.founder_name}"
    )
    html_body = (
        f"<p>Hi {name or 'there'},</p>"
        "<p>Welcome to BrainAPI! Your API key is ready to use.</p>"
        f"<p><strong>API key:</strong> {api_key}</p>"
        f"<p><strong>Trial ends:</strong> {_format_trial_end(trial_ends_at)}</p>"
        f"<p><a href=\"{_absolute_url('/ui/onboarding.html')}\">Get started with the quickstart guide</a></p>"
        f"<p>Cheers,<br>{settings.founder_name}</p>"
    )
    return queue_email_event(
        event_type="welcome",
        recipient_email=email,
        subject=subject,
        body_text=body_text,
        html_body=html_body,
        dedupe_key=f"welcome:{email}",
    )


def queue_payment_success_email(*, name: Optional[str], email: str, plan_name: str, amount_inr: Optional[float] = None) -> dict[str, Any]:
    subject = "BrainAPI Payment Successful"
    body_text = (
        f"Hi {name or 'there'},\n\n"
        f"Thank you for upgrading to {plan_name}.\n"
        f"Plan amount: {_format_inr(amount_inr)}\n\n"
        "Your account has been updated with the new limits immediately.\n\n"
        f"Cheers,\n{settings.founder_name}"
    )
    html_body = (
        f"<p>Hi {name or 'there'},</p>"
        f"<p>Thank you for upgrading to <strong>{plan_name}</strong>.</p>"
        f"<p><strong>Plan amount:</strong> {_format_inr(amount_inr)}</p>"
        "<p>Your account has been updated with the new limits immediately.</p>"
        f"<p>Cheers,<br>{settings.founder_name}</p>"
    )
    return queue_email_event(
        event_type="payment_success",
        recipient_email=email,
        subject=subject,
        body_text=body_text,
        html_body=html_body,
        dedupe_key=f"payment_success:{email}:{plan_name}",
    )


def queue_invoice_email(
    *,
    name: Optional[str],
    email: str,
    plan_name: str,
    amount_inr: Optional[float],
    razorpay_payment_id: str,
    razorpay_order_id: str,
) -> dict[str, Any]:
    amount_display = _format_inr(amount_inr)
    subject = f"BrainAPI Invoice - {plan_name} - {amount_display}"
    body_text = (
        f"Hi {name or 'there'},\n\n"
        f"Thanks for your payment of {amount_display} for {plan_name}.\n"
        f"Payment ID: {razorpay_payment_id}\n"
        f"Order ID: {razorpay_order_id}\n\n"
        "You can download your invoice anytime from the BrainAPI dashboard.\n\n"
        f"Cheers,\n{settings.founder_name}"
    )
    html_body = (
        f"<p>Hi {name or 'there'},</p>"
        f"<p>Thanks for your payment of <strong>{amount_display}</strong> for <strong>{plan_name}</strong>.</p>"
        f"<p><strong>Payment ID:</strong> {razorpay_payment_id}<br><strong>Order ID:</strong> {razorpay_order_id}</p>"
        f"<p>You can download your invoice anytime from the <a href=\"{_absolute_url('/ui/dashboard.html')}\">BrainAPI dashboard</a>.</p>"
        f"<p>Cheers,<br>{settings.founder_name}</p>"
    )
    return queue_email_event(
        event_type="invoice",
        recipient_email=email,
        subject=subject,
        body_text=body_text,
        html_body=html_body,
        dedupe_key=f"invoice:{email}:{razorpay_order_id}:{razorpay_payment_id}",
    )


def schedule_trial_reminder_emails() -> dict[str, Any]:
    skip_reason = _environment_skip_reason()
    if skip_reason:
        return {"status": "skipped", "scheduled": 0, "reason": skip_reason}

    # Reminder scheduling can be implemented with cron jobs or workers.
    return {"status": "skipped", "scheduled": 0, "reason": "no_reminders_configured"}


def send_pending_emails(limit: int = 50) -> dict[str, Any]:
    with SessionLocal() as db:
        pending_events = db.scalars(
            select(EmailEvent)
            .where(EmailEvent.status.in_(("queued", "scheduled")))
            .order_by(EmailEvent.created_at.asc())
            .limit(limit)
        ).all()

    processed = 0
    sent = 0
    failed = 0
    skipped = 0

    for event in pending_events:
        processed += 1
        result = dispatch_transactional_email(event.id)
        if result.get("success"):
            sent += 1
        elif result.get("status") == "skipped":
            skipped += 1
        else:
            failed += 1

    return {"processed": processed, "sent": sent, "failed": failed, "skipped": skipped}


def process_email_queue(limit: int = 50) -> dict[str, Any]:
    return send_pending_emails(limit=limit)
