from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from app.config import settings

from .configuration import RoutingConfig
from .costing import estimate_cost, estimate_tokens_from_text
from .types import NormalizedRequest, ProviderResponse
from .providers.base import AIProvider

logger = logging.getLogger("brainapi.ai")


class RoutingError(Exception):
    def __init__(self, detail: str, *, status_code: int = 500, attempted_providers: list[str] | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.attempted_providers = attempted_providers or []


@dataclass
class ProviderStats:
    latency_ema_ms: float | None = None
    success_count: int = 0
    error_count: int = 0

    def record_success(self, latency_ms: int) -> None:
        self.success_count += 1
        if self.latency_ema_ms is None:
            self.latency_ema_ms = float(latency_ms)
            return
        # Exponential moving average (alpha=0.2)
        self.latency_ema_ms = (0.8 * self.latency_ema_ms) + (0.2 * float(latency_ms))

    def record_error(self) -> None:
        self.error_count += 1


class ProviderRouter:
    """Routes requests across providers with mode-based ordering + automatic fallback."""

    def __init__(self, providers: dict[str, AIProvider], config: RoutingConfig) -> None:
        self.providers = providers
        self.config = config
        self.stats: dict[str, ProviderStats] = {name: ProviderStats() for name in providers}

    def _enabled(self, provider: str) -> bool:
        profile = self.config.providers.get(provider)
        if profile is None:
            return True
        return bool(profile.enabled)

    def _provider_timeout_seconds(self, provider: str) -> float:
        profile = self.config.providers.get(provider)
        return float(profile.timeout_seconds) if profile else 20.0

    def _status_code_from_exception(self, exc: Exception) -> int:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            return int(exc.response.status_code)

        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int) and 400 <= status_code <= 599:
            return status_code

        message = str(exc).lower()
        if "not configured" in message:
            return 503
        if "timeout" in message or "timed out" in message:
            return 504
        return 500

    def _candidates_for_request(self, request: NormalizedRequest, mode: str) -> list[str]:
        capability = request.request_type

        # Legacy / global force-provider mode. Keeps backward compatibility.
        forced = settings.provider_name
        if forced != "auto":
            if forced in self.providers and self.providers[forced].supports(capability):
                return [forced]
            return []

        override = (
            self.config.mode_overrides.get(mode, {}).get(capability)
            if isinstance(self.config.mode_overrides.get(mode, {}), dict)
            else None
        )
        if override:
            return [p for p in override if p in self.providers]

        # Default ordering for legacy "auto" mode: preserve the old PROVIDER_FALLBACK_ORDER.
        requested = settings.provider_fallback_order_list
        ordered = [p for p in requested if p in self.providers]

        # Bring in configured providers that were omitted from PROVIDER_FALLBACK_ORDER
        # so new providers can participate without forcing env changes.
        for provider_name in self.providers:
            if provider_name not in ordered:
                ordered.append(provider_name)

        return ordered

    def _sort_candidates(self, candidates: list[str], request: NormalizedRequest, mode: str) -> list[str]:
        capability = request.request_type

        # If the config explicitly defined an order, keep it.
        override = (
            self.config.mode_overrides.get(mode, {}).get(capability)
            if isinstance(self.config.mode_overrides.get(mode, {}), dict)
            else None
        )
        if override:
            return [p for p in override if p in candidates]

        def cost_score(p: str) -> float:
            """Lower is cheaper.

            For text requests we can estimate tokens and apply configured pricing.
            If pricing is missing we fall back to a static cost_rank.
            """

            profile = self.config.providers.get(p)
            if not profile:
                return 9999.0

            if request.request_type == "text" and (profile.input_cost_per_1k or profile.output_cost_per_1k):
                estimated_tokens = estimate_tokens_from_text(request.prompt or "") + int(request.max_output_tokens or 0)
                cost = estimate_cost(self.config, p, max(1, int(estimated_tokens)))
                if cost > 0:
                    return float(cost)

            return float(profile.cost_rank)

        def speed_score(p: str) -> float:
            stat = self.stats.get(p)
            if stat and stat.latency_ema_ms is not None:
                return float(stat.latency_ema_ms)
            profile = self.config.providers.get(p)
            return float(profile.latency_hint_ms) if profile else 9999.0

        def quality_score(p: str) -> float:
            profile = self.config.providers.get(p)
            if not profile:
                return 0.0
            return float(profile.quality_rank)

        if mode == "cheap":
            return sorted(candidates, key=cost_score)
        if mode == "fast":
            return sorted(candidates, key=speed_score)
        if mode == "best":
            return sorted(candidates, key=lambda p: (-quality_score(p), speed_score(p)))

        # auto mode: simple weighted score.
        # Lower is better.
        def auto_score(p: str) -> float:
            # cost_score may be a rank (images/audio) or a dollar amount (text).
            # Convert tiny dollar amounts into a roughly rank-like scale.
            cost_component = cost_score(p)
            if cost_component < 1.0:
                cost_component = cost_component * 1000.0

            return (0.45 * cost_component) + (0.25 * speed_score(p) / 1000.0) + (0.30 * (10.0 - quality_score(p)))

        return sorted(candidates, key=auto_score)

    def route(self, request: NormalizedRequest, mode: str) -> tuple[ProviderResponse, bool]:
        mode_norm = (mode or self.config.default_mode or "cheap").strip().lower()
        if mode_norm == "legacy":
            # Preserve PROVIDER_FALLBACK_ORDER exactly (no scoring/sorting).
            pass
        elif mode_norm not in {"cheap", "fast", "best", "auto"}:
            mode_norm = self.config.default_mode

        candidates = self._candidates_for_request(request, mode_norm)
        candidates = [p for p in candidates if p in self.providers]
        if settings.provider_name == "auto":
            candidates = [p for p in candidates if self._enabled(p)]
        candidates = [p for p in candidates if self.providers[p].supports(request.request_type)]

        if not candidates:
            raise RoutingError(
                f"No providers available for {request.request_type}",
                status_code=503,
            )

        ordered = candidates if mode_norm == "legacy" else self._sort_candidates(candidates, request, mode_norm)

        errors: list[tuple[str, Exception]] = []
        for index, provider_name in enumerate(ordered):
            provider = self.providers[provider_name]
            if not provider.is_configured():
                errors.append((provider_name, RuntimeError("provider not configured")))
                continue

            started = time.perf_counter()
            try:
                response = provider.invoke(request)
                # Record latency including our overhead.
                total_latency_ms = max(response.latency_ms, int((time.perf_counter() - started) * 1000))
                response.latency_ms = total_latency_ms

                self.stats[provider_name].record_success(total_latency_ms)
                fallback_used = index > 0

                logger.info(
                    "ai_call type=%s mode=%s provider=%s model=%s latency_ms=%s tokens=%s cost=%s fallback=%s",
                    request.request_type,
                    mode_norm,
                    response.provider,
                    response.model,
                    response.latency_ms,
                    response.tokens_used,
                    response.cost_estimate,
                    fallback_used,
                )

                if fallback_used:
                    logger.warning(
                        "ai_fallback type=%s mode=%s used_provider=%s attempted=%s",
                        request.request_type,
                        mode_norm,
                        response.provider,
                        [p for p, _ in errors] + [provider_name],
                    )

                return response, fallback_used

            except Exception as exc:
                self.stats[provider_name].record_error()
                errors.append((provider_name, exc))

        last_provider, last_exc = errors[-1]
        attempted = [p for p, _ in errors]
        logger.error(
            "ai_all_providers_failed type=%s mode=%s attempts=%s last_provider=%s error=%s",
            request.request_type,
            mode_norm,
            attempted,
            last_provider,
            last_exc,
        )

        status_code = self._status_code_from_exception(last_exc)
        if errors and all("not configured" in str(exc).lower() for _, exc in errors):
            status_code = 503

        raise RoutingError(
            "All providers failed",
            status_code=status_code,
            attempted_providers=attempted,
        ) from last_exc
