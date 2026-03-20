from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Literal

from ..types import NormalizedRequest, ProviderResponse

Capability = Literal["text", "image", "audio"]


@dataclass(frozen=True)
class ProviderCapabilities:
    text: bool = False
    image: bool = False
    audio: bool = False


class UnsupportedProviderCapability(NotImplementedError):
    """Raised when a provider does not implement a requested capability."""


class AIProvider(abc.ABC):
    """A standard interface for all providers."""

    name: str
    capabilities: ProviderCapabilities

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Return True when auth/credentials are available."""

    def supports(self, capability: Capability) -> bool:
        """Return True when this provider can satisfy the request type."""
        return bool(getattr(self.capabilities, capability, False))

    def generateText(self, request: NormalizedRequest) -> ProviderResponse:
        raise UnsupportedProviderCapability(f"{self.name} does not support text generation")

    def generateImage(self, request: NormalizedRequest) -> ProviderResponse:
        raise UnsupportedProviderCapability(f"{self.name} does not support image generation")

    def transcribeAudio(self, request: NormalizedRequest) -> ProviderResponse:
        raise UnsupportedProviderCapability(f"{self.name} does not support audio transcription")

    def invoke(self, request: NormalizedRequest) -> ProviderResponse:
        """Execute the request and return a normalized response."""
        if request.request_type == "text":
            return self.generateText(request)
        if request.request_type == "image":
            return self.generateImage(request)
        if request.request_type == "audio":
            return self.transcribeAudio(request)
        raise ValueError(f"Unsupported request type: {request.request_type}")
