from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

AIRequestType = Literal["text", "image", "audio"]
AIRoutingMode = Literal["cheap", "fast", "best", "auto"]


class UnifiedAIRequest(BaseModel):
    """Unified request shape for /api/v1/ai.

    Notes:
    - For type="text" and type="image": input is the prompt.
    - For type="audio": input is base64-encoded audio bytes.

    Optional knobs exist for better control while keeping the core contract small.
    """

    type: AIRequestType
    input: str = Field(min_length=1)
    mode: AIRoutingMode | None = None

    # Optional tuning for text
    temperature: float | None = Field(default=0.7, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=300, ge=1, le=4000)

    # Optional tuning for images
    size: Literal["256x256", "512x512", "1024x1024", "1024x1536", "1536x1024"] | None = None

    # Optional metadata for audio
    audio_filename: str | None = "audio"
    audio_content_type: str | None = None


class UnifiedAIResponse(BaseModel):
    success: bool = True
    output: str
    provider: str
    tokens_used: int = 0
    cost_estimate: float = 0.0

    # Extra observability fields (kept optional to avoid breaking consumers)
    model: str | None = None
    latency_ms: int | None = None
    fallback_used: bool = False


@dataclass(frozen=True)
class NormalizedRequest:
    request_type: AIRequestType
    prompt: str | None = None
    audio_bytes: bytes | None = None
    audio_filename: str | None = None
    audio_content_type: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    image_size: str | None = None


@dataclass
class ProviderResponse:
    output: str
    provider: str
    model: str
    tokens_used: int
    cost_estimate: float
    latency_ms: int
    raw: dict[str, Any] | None = None
