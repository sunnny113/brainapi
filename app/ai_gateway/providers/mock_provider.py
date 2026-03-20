from __future__ import annotations

import time

from .base import AIProvider, ProviderCapabilities
from ..types import NormalizedRequest, ProviderResponse


class MockProvider(AIProvider):
    name = "mock"
    capabilities = ProviderCapabilities(text=True, image=True, audio=True)

    def is_configured(self) -> bool:
        return True

    def generateText(self, request: NormalizedRequest) -> ProviderResponse:
        started = time.perf_counter()
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ProviderResponse(
            output=f"[mock] {request.prompt or ''}"[:2000],
            provider=self.name,
            model="mock-text-v1",
            tokens_used=0,
            cost_estimate=0.0,
            latency_ms=latency_ms,
            raw=None,
        )

    def generateImage(self, request: NormalizedRequest) -> ProviderResponse:
        started = time.perf_counter()
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ProviderResponse(
            output="https://placehold.co/512x512",
            provider=self.name,
            model="mock-image-v1",
            tokens_used=0,
            cost_estimate=0.0,
            latency_ms=latency_ms,
            raw=None,
        )

    def transcribeAudio(self, request: NormalizedRequest) -> ProviderResponse:
        started = time.perf_counter()
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ProviderResponse(
            output="mock transcription",
            provider=self.name,
            model="mock-audio-v1",
            tokens_used=0,
            cost_estimate=0.0,
            latency_ms=latency_ms,
            raw=None,
        )
