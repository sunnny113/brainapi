from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from functools import lru_cache

from app.config import settings

from .cache import TTLCache
from .configuration import load_routing_config
from .costing import estimate_cost, estimate_tokens_from_text
from .providers.anthropic_provider import AnthropicProvider
from .providers.mock_provider import MockProvider
from .providers.openai_provider import OpenAIProvider
from .router import ProviderRouter
from .types import NormalizedRequest, ProviderResponse, UnifiedAIRequest

logger = logging.getLogger("brainapi.ai")


@dataclass
class AIGateway:
    router: ProviderRouter
    cache: TTLCache | None

    def _cache_key(self, request: NormalizedRequest, mode: str) -> str:
        parts = [
            request.request_type,
            mode,
            str(request.temperature or ""),
            str(request.max_output_tokens or ""),
            str(request.image_size or ""),
            request.prompt or "",
        ]
        return "|".join(parts)[:2048]

    def _normalize(self, payload: UnifiedAIRequest) -> tuple[NormalizedRequest, str]:
        mode = (payload.mode or "").strip().lower() or ""

        if payload.type == "text":
            return (
                NormalizedRequest(
                    request_type="text",
                    prompt=payload.input,
                    temperature=payload.temperature,
                    max_output_tokens=payload.max_output_tokens,
                ),
                mode,
            )

        if payload.type == "image":
            return (
                NormalizedRequest(
                    request_type="image",
                    prompt=payload.input,
                    image_size=payload.size,
                ),
                mode,
            )

        if payload.type == "audio":
            # JSON-friendly API: audio must be base64.
            try:
                audio_bytes = base64.b64decode(payload.input, validate=True)
            except Exception as exc:
                raise ValueError("Audio input must be base64-encoded bytes") from exc

            return (
                NormalizedRequest(
                    request_type="audio",
                    audio_bytes=audio_bytes,
                    audio_filename=payload.audio_filename,
                    audio_content_type=payload.audio_content_type,
                ),
                mode,
            )

        raise ValueError("Invalid request type")

    def _apply_costing(self, response: ProviderResponse, request: NormalizedRequest) -> ProviderResponse:
        tokens_used = response.tokens_used
        if tokens_used <= 0 and request.request_type == "text":
            # Estimate tokens if provider didn't return usage.
            tokens_used = estimate_tokens_from_text(request.prompt or "") + int(request.max_output_tokens or 0)

        response.tokens_used = int(tokens_used)
        response.cost_estimate = estimate_cost(self.router.config, response.provider, response.tokens_used)
        return response

    def handle(self, payload: UnifiedAIRequest) -> tuple[ProviderResponse, bool]:
        request, mode = self._normalize(payload)
        effective_mode = mode or self.router.config.default_mode

        if self.cache and request.request_type == "text":
            key = self._cache_key(request, effective_mode)
            cached = self.cache.get(key)
            if isinstance(cached, ProviderResponse):
                return cached, False

        response, fallback_used = self.router.route(request, effective_mode)
        response = self._apply_costing(response, request)

        if self.cache and request.request_type == "text":
            key = self._cache_key(request, effective_mode)
            self.cache.set(key, response)

        return response, fallback_used


@lru_cache
def get_gateway() -> AIGateway:
    config = load_routing_config(settings.routing_config_path)

    providers = {
        "mock": MockProvider(),
        "openai": OpenAIProvider(),
        "anthropic": AnthropicProvider(),
    }

    router = ProviderRouter(providers=providers, config=config)

    cache = None
    if config.enable_cache:
        cache = TTLCache(max_items=1024, ttl_seconds=config.cache_ttl_seconds)

    logger.info(
        "ai_gateway_ready provider_mode=%s routing_default_mode=%s config_path=%s",
        settings.provider_name,
        config.default_mode,
        settings.routing_config_path,
    )

    return AIGateway(router=router, cache=cache)
