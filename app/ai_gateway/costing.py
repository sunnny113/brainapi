from __future__ import annotations

from dataclasses import dataclass

from .configuration import ProviderProfile, RoutingConfig


def estimate_tokens_from_text(text: str) -> int:
    """Cheap token estimator used when providers don't return usage.

    We intentionally keep this dependency-free.
    """

    if not text:
        return 0
    # Very rough heuristic: ~4 chars per token for English.
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class CostBreakdown:
    tokens_used: int
    cost_estimate: float


def estimate_cost(config: RoutingConfig, provider: str, tokens_used: int) -> float:
    profile: ProviderProfile | None = config.providers.get(provider)
    if profile is None:
        return 0.0

    # If we don't know prompt vs completion split, assume 50/50.
    input_tokens = tokens_used // 2
    output_tokens = tokens_used - input_tokens

    cost = (input_tokens / 1000.0) * float(profile.input_cost_per_1k) + (output_tokens / 1000.0) * float(
        profile.output_cost_per_1k
    )
    return float(round(cost, 8))
