from __future__ import annotations

import time

import httpx

from app.config import settings

from .base import AIProvider, ProviderCapabilities
from ..types import NormalizedRequest, ProviderResponse


class AnthropicProvider(AIProvider):
    name = "anthropic"
    capabilities = ProviderCapabilities(text=True, image=False, audio=False)

    def __init__(self) -> None:
        self._base_url = (settings.anthropic_base_url or "https://api.anthropic.com").rstrip("/")
        self._timeout = httpx.Timeout(20.0)

    def is_configured(self) -> bool:
        return bool((settings.anthropic_api_key or "").strip())

    def generateText(self, request: NormalizedRequest) -> ProviderResponse:
        if not self.is_configured():
            raise RuntimeError("Anthropic API key not configured")

        started = time.perf_counter()

        url = f"{self._base_url}/v1/messages"
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": settings.anthropic_text_model,
            "max_tokens": int(request.max_output_tokens or 300),
            "temperature": float(request.temperature or 0.7),
            "messages": [
                {
                    "role": "user",
                    "content": request.prompt or "",
                }
            ],
        }

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            body = resp.json()

        # Anthropic responses contain a list of content blocks.
        blocks = body.get("content") or []
        parts: list[str] = []
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        output = "".join(parts).strip()

        usage = body.get("usage") or {}
        tokens_used = int((usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))

        latency_ms = int((time.perf_counter() - started) * 1000)

        return ProviderResponse(
            output=output,
            provider=self.name,
            model=settings.anthropic_text_model,
            tokens_used=tokens_used,
            cost_estimate=0.0,
            latency_ms=latency_ms,
            raw=None,
        )
