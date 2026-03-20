from __future__ import annotations

import base64
import time
from io import BytesIO

from openai import OpenAI

from app.config import settings

from .base import AIProvider, ProviderCapabilities
from ..types import NormalizedRequest, ProviderResponse


class OpenAIProvider(AIProvider):
    name = "openai"
    capabilities = ProviderCapabilities(text=True, image=True, audio=True)

    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.openai_api_key)

    def is_configured(self) -> bool:
        return bool((settings.openai_api_key or "").strip())

    def _extract_text(self, content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text") or ""))
                    continue
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
            return "".join(parts)
        return str(content or "")

    def generateText(self, request: NormalizedRequest) -> ProviderResponse:
        started = time.perf_counter()
        response = self._client.chat.completions.create(
            model=settings.openai_text_model,
            messages=[{"role": "user", "content": request.prompt or ""}],
            temperature=float(request.temperature or 0.7),
            max_tokens=int(request.max_output_tokens or 300),
        )

        output = ""
        if response.choices:
            message = response.choices[0].message
            if message and message.content:
                output = self._extract_text(message.content)

        usage = getattr(response, "usage", None)
        tokens_used = int(getattr(usage, "total_tokens", 0) or 0)
        latency_ms = int((time.perf_counter() - started) * 1000)

        return ProviderResponse(
            output=output,
            provider=self.name,
            model=settings.openai_text_model,
            tokens_used=tokens_used,
            cost_estimate=0.0,
            latency_ms=latency_ms,
            raw=None,
        )

    def generateImage(self, request: NormalizedRequest) -> ProviderResponse:
        started = time.perf_counter()
        size = request.image_size or "1024x1024"
        response = self._client.images.generate(
            model=settings.openai_image_model,
            prompt=request.prompt or "",
            size=size,
        )

        image_url = None
        image_b64 = None
        if response.data:
            image_url = response.data[0].url
            image_b64 = response.data[0].b64_json

        if image_url:
            output = image_url
        elif image_b64:
            output = f"data:image/png;base64,{image_b64}"
        else:
            output = ""

        latency_ms = int((time.perf_counter() - started) * 1000)

        return ProviderResponse(
            output=output,
            provider=self.name,
            model=settings.openai_image_model,
            tokens_used=0,
            cost_estimate=0.0,
            latency_ms=latency_ms,
            raw=None,
        )

    def transcribeAudio(self, request: NormalizedRequest) -> ProviderResponse:
        if not request.audio_bytes:
            raise ValueError("audio_bytes missing")

        started = time.perf_counter()
        file_tuple = (
            request.audio_filename or "audio",
            BytesIO(request.audio_bytes),
            request.audio_content_type or "application/octet-stream",
        )

        transcript = self._client.audio.transcriptions.create(
            model=settings.openai_transcription_model,
            file=file_tuple,
        )

        latency_ms = int((time.perf_counter() - started) * 1000)

        return ProviderResponse(
            output=transcript.text,
            provider=self.name,
            model=settings.openai_transcription_model,
            tokens_used=0,
            cost_estimate=0.0,
            latency_ms=latency_ms,
            raw=None,
        )
