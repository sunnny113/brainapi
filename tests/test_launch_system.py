import os
from datetime import datetime, timezone

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
os.environ.setdefault("TRIAL_SIGNUP_ENABLED", "true")

from app.main import app  # noqa: E402


client = TestClient(app)


def unique_email(prefix: str = "launch") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}-{timestamp}@brainapi.site"


def test_root_and_status_pages_render():
    root_response = client.get("/")
    assert root_response.status_code == 200
    assert "Get API Key" in root_response.text

    status_response = client.get("/status")
    assert status_response.status_code == 200
    assert "Current service health" in status_response.text


def test_public_status_and_plan_endpoints():
    status_response = client.get("/api/v1/public/status")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["success"] is True
    assert status_body["support_email"]
    assert status_body["docs_url"] == "/ui/quickstart.html"

    plans_response = client.get("/api/v1/public/plans")
    assert plans_response.status_code == 200
    plans_body = plans_response.json()
    prices = {item["name"]: item["price_inr"] for item in plans_body["plans"]}
    assert prices["Starter"] == 499
    assert prices["Pro"] == 999


def test_auth_signup_returns_onboarding_metadata():
    email = unique_email("onboarding")
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Launch User",
            "email": email,
            "password": "StrongPass123!",
            "newsletter_opt_in": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["api_key"].startswith("brn_")
    assert body["quickstart_url"] == "/ui/onboarding.html"
    assert body["dashboard_url"] == "/ui/dashboard.html#overview"
    assert body["support_email"]


def test_admin_launch_metrics_endpoint():
    email = unique_email("metrics")
    signup_response = client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Metrics User",
            "email": email,
            "password": "StrongPass123!",
            "newsletter_opt_in": False,
        },
    )
    assert signup_response.status_code == 200

    metrics_response = client.get(
        "/api/v1/admin/launch-metrics?days=30",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert metrics_response.status_code == 200
    body = metrics_response.json()
    assert body["window_days"] == 30
    assert body["signups"] >= 1
    assert "api_calls" in body
    assert "failed_emails" in body
    assert "conversion_rate" in body
