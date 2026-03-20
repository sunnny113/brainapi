import json
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

from app.ai_gateway.configuration import ProviderProfile, RoutingConfig
from app.ai_gateway.gateway import get_gateway
from app.ai_gateway.providers.base import AIProvider, ProviderCapabilities
from app.ai_gateway.router import ProviderRouter
from app.ai_gateway.types import NormalizedRequest, ProviderResponse
from app.config import settings
from app.main import app


client = TestClient(app)


class StaticProvider(AIProvider):
    def __init__(self, name: str, latency_ms: int) -> None:
        self.name = name
        self.capabilities = ProviderCapabilities(text=True)
        self._latency_ms = latency_ms

    def is_configured(self) -> bool:
        return True

    def generateText(self, request: NormalizedRequest) -> ProviderResponse:
        return ProviderResponse(
            output=f"{self.name}:{request.prompt}",
            provider=self.name,
            model=f"{self.name}-model",
            tokens_used=64,
            cost_estimate=0.0,
            latency_ms=self._latency_ms,
            raw=None,
        )


def setup_function() -> None:
    get_gateway.cache_clear()


def test_unified_ai_text_mock_success(monkeypatch):
    monkeypatch.setattr(settings, "provider", "mock")
    get_gateway.cache_clear()

    response = client.post(
        "/api/v1/ai",
        headers={"X-API-Key": "test-user-key"},
        json={"type": "text", "input": "hello", "mode": "cheap", "max_output_tokens": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["provider"] == "mock"
    assert "hello" in body["output"]
    assert body["tokens_used"] > 0


def test_unified_ai_routing_fallback_to_mock(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "provider", "auto")

    config_path = tmp_path / "routing.json"
    config_path.write_text(
        json.dumps(
            {
                "providers": ["anthropic", "mock"],
                "routing": {
                    "default_mode": "cheap",
                    "mode_overrides": {"cheap": {"text": ["anthropic", "mock"]}},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "routing_config_path", str(config_path))
    get_gateway.cache_clear()

    response = client.post(
        "/api/v1/ai",
        headers={"X-API-Key": "test-user-key"},
        json={"type": "text", "input": "hello", "mode": "cheap", "max_output_tokens": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["fallback_used"] is True


def test_unified_ai_token_limit_enforced(monkeypatch):
    monkeypatch.setattr(settings, "provider", "mock")
    monkeypatch.setattr(settings, "max_tokens_per_request", 5)
    get_gateway.cache_clear()

    response = client.post(
        "/api/v1/ai",
        headers={"X-API-Key": "test-user-key"},
        json={"type": "text", "input": "hello", "mode": "cheap", "max_output_tokens": 10},
    )

    assert response.status_code == 400
    assert "max token budget" in response.json()["detail"]


def test_legacy_text_endpoint_uses_gateway(monkeypatch):
    monkeypatch.setattr(settings, "provider", "mock")
    get_gateway.cache_clear()

    response = client.post(
        "/api/v1/text/generate",
        headers={"X-API-Key": "test-user-key"},
        json={"prompt": "legacy hello", "max_output_tokens": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert "legacy hello" in body["text"]


def test_router_prefers_cost_speed_and_quality(monkeypatch):
    monkeypatch.setattr(settings, "provider", "auto")

    providers = {
        "openai": StaticProvider("openai", latency_ms=120),
        "anthropic": StaticProvider("anthropic", latency_ms=650),
    }
    config = RoutingConfig(
        default_mode="cheap",
        providers={
            "openai": ProviderProfile(
                enabled=True,
                cost_rank=1,
                speed_rank=1,
                quality_rank=4,
                input_cost_per_1k=0.00015,
                output_cost_per_1k=0.0006,
                latency_hint_ms=120,
            ),
            "anthropic": ProviderProfile(
                enabled=True,
                cost_rank=3,
                speed_rank=2,
                quality_rank=5,
                input_cost_per_1k=0.00025,
                output_cost_per_1k=0.00125,
                latency_hint_ms=650,
            ),
        },
    )
    router = ProviderRouter(providers=providers, config=config)
    request = NormalizedRequest(
        request_type="text",
        prompt="route me",
        max_output_tokens=128,
    )

    cheap, _ = router.route(request, "cheap")
    fast, _ = router.route(request, "fast")
    best, _ = router.route(request, "best")

    assert cheap.provider == "openai"
    assert fast.provider == "openai"
    assert best.provider == "anthropic"
