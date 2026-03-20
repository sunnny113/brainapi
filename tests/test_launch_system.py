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
from app.db import init_db  # noqa: E402


init_db()

client = TestClient(app)


def unique_email(prefix: str = "launch") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}-{timestamp}@brainapi.site"


def test_root_and_status_pages_render():
    root_response = client.get("/")
    assert root_response.status_code == 200
    assert "Get API Key" in root_response.text
    assert "AI memory API for chatbots, agents, and persistent context workflows." in root_response.text

    status_response = client.get("/status")
    assert status_response.status_code == 200
    assert "Current service health" in status_response.text

    blog_response = client.get("/blog")
    assert blog_response.status_code == 200
    assert "Guides for AI memory API workflows" in blog_response.text

    page_response = client.get("/chatbot-memory-api")
    assert page_response.status_code == 200
    assert "Build a chatbot memory API workflow" in page_response.text

    article_response = client.get("/blog/store-ai-context-nodejs")
    assert article_response.status_code == 200
    assert "How to store AI context in Node.js" in article_response.text

    quickstart_response = client.get("/ui/quickstart.html")
    assert quickstart_response.status_code == 200
    assert "Memory and chatbot resources" in quickstart_response.text


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

    sitemap_response = client.get("/sitemap.xml")
    assert sitemap_response.status_code == 200
    assert "/blog" in sitemap_response.text
    assert "/chatbot-memory-api" in sitemap_response.text
    assert "/memory-api-for-ai-agents" in sitemap_response.text
    assert "/ui/login.html" not in sitemap_response.text

    robots_response = client.get("/robots.txt")
    assert robots_response.status_code == 200
    assert "Disallow: /ui/login.html" in robots_response.text
    assert "Disallow: /ui/dashboard.html" in robots_response.text


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
