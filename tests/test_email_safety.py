import os

from fastapi.testclient import TestClient

os.environ.setdefault("PROVIDER", "mock")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("REQUIRE_API_KEY", "true")
os.environ.setdefault("API_KEYS", "test-user-key")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_brainapi.db")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("ENABLE_USAGE_METERING", "true")
os.environ.setdefault("AUTO_CREATE_TABLES", "true")

from app.config import settings
from app.emails import queue_email_event
from app.main import app


client = TestClient(app)


def test_queue_email_event_rejects_blocked_domain():
    result = queue_email_event(
        event_type="custom",
        recipient_email="blocked@example.com",
        subject="Hello",
        body_text="Test message",
    )

    assert result["success"] is False
    assert result["status"] == "skipped"
    assert result["id"] is None
    assert "blocked" in (result["error"] or "").lower()


def test_send_email_endpoint_blocks_dummy_domain():
    response = client.post(
        "/send-email",
        headers={"X-API-Key": "test-user-key"},
        json={
            "email": "blocked@example.com",
            "subject": "Test",
            "message": "Hello",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "Email skipped."
    assert "blocked" in (body["error"] or "").lower()


def test_send_email_endpoint_skips_in_development(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "skip_email_in_development", True)

    response = client.post(
        "/send-email",
        headers={"X-API-Key": "test-user-key"},
        json={
            "email": "customer@brainapi.site",
            "subject": "Test",
            "message": "Hello",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "Email skipped in development mode."
    assert body["error"] is None
