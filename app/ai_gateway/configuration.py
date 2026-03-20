from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderProfile:
    enabled: bool = True

    # Rankings: lower is "better" for cost/speed; higher is "better" for quality.
    cost_rank: float = 1.0
    speed_rank: float = 1.0
    quality_rank: float = 1.0

    # Rough pricing in USD per 1K tokens.
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0

    # Used when we don't yet have runtime latency stats.
    latency_hint_ms: int = 1500

    timeout_seconds: float = 20.0


@dataclass
class RoutingConfig:
    default_mode: str = "cheap"

    # Optional explicit provider orders per mode/capability.
    # Example:
    #   mode_overrides = {"cheap": {"text": ["anthropic", "openai"]}}
    mode_overrides: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    # Provider profiles keyed by provider name.
    providers: dict[str, ProviderProfile] = field(default_factory=dict)

    enable_cache: bool = False
    cache_ttl_seconds: int = 60


DEFAULT_CONFIG = RoutingConfig(
    default_mode="cheap",
    providers={
        "openai": ProviderProfile(
            enabled=True,
            cost_rank=2,
            speed_rank=2,
            quality_rank=4,
            input_cost_per_1k=0.00015,
            output_cost_per_1k=0.0006,
            latency_hint_ms=1200,
            timeout_seconds=20.0,
        ),
        "anthropic": ProviderProfile(
            enabled=True,
            cost_rank=3,
            speed_rank=2,
            quality_rank=5,
            input_cost_per_1k=0.00025,
            output_cost_per_1k=0.00125,
            latency_hint_ms=1400,
            timeout_seconds=20.0,
        ),
        "mock": ProviderProfile(
            enabled=True,
            cost_rank=0,
            speed_rank=0,
            quality_rank=0,
            input_cost_per_1k=0.0,
            output_cost_per_1k=0.0,
            latency_hint_ms=1,
            timeout_seconds=1.0,
        ),
    },
)


def _coerce_provider_profile(name: str, payload: dict[str, Any]) -> ProviderProfile:
    def _float(key: str, default: float) -> float:
        value = payload.get(key, default)
        try:
            return float(value)
        except Exception:
            return default

    def _int(key: str, default: int) -> int:
        value = payload.get(key, default)
        try:
            return int(value)
        except Exception:
            return default

    profile = ProviderProfile(
        enabled=bool(payload.get("enabled", True)),
        cost_rank=_float("cost_rank", DEFAULT_CONFIG.providers.get(name, ProviderProfile()).cost_rank),
        speed_rank=_float("speed_rank", DEFAULT_CONFIG.providers.get(name, ProviderProfile()).speed_rank),
        quality_rank=_float("quality_rank", DEFAULT_CONFIG.providers.get(name, ProviderProfile()).quality_rank),
        input_cost_per_1k=_float("input_cost_per_1k", DEFAULT_CONFIG.providers.get(name, ProviderProfile()).input_cost_per_1k),
        output_cost_per_1k=_float("output_cost_per_1k", DEFAULT_CONFIG.providers.get(name, ProviderProfile()).output_cost_per_1k),
        latency_hint_ms=_int("latency_hint_ms", DEFAULT_CONFIG.providers.get(name, ProviderProfile()).latency_hint_ms),
        timeout_seconds=_float("timeout_seconds", DEFAULT_CONFIG.providers.get(name, ProviderProfile()).timeout_seconds),
    )
    return profile


def load_routing_config(path: str | None) -> RoutingConfig:
    """Load routing config from a JSON file.

    The file is optional; when missing or invalid, DEFAULT_CONFIG is used.

    Supported shapes:

    1) Simple list:
        {"providers": ["openai", "anthropic"], "routing": {"default_mode": "cheap"}}

    2) Detailed profiles:
        {
          "providers": {
            "openai": {"enabled": true, "cost_rank": 2, "quality_rank": 4, ...},
            "anthropic": {...}
          },
          "routing": {
            "default_mode": "auto",
            "mode_overrides": {"cheap": {"text": ["anthropic", "openai"]}}
          }
        }
    """

    if not path:
        return DEFAULT_CONFIG

    config_path = Path(path)
    if not config_path.exists():
        return DEFAULT_CONFIG

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_CONFIG

    routing = raw.get("routing", {}) if isinstance(raw, dict) else {}

    providers_section = raw.get("providers") if isinstance(raw, dict) else None
    providers: dict[str, ProviderProfile] = dict(DEFAULT_CONFIG.providers)

    if isinstance(providers_section, list):
        # Enable only listed providers, with default profiles where possible.
        allow = {str(p).strip().lower() for p in providers_section if str(p).strip()}
        for name in list(providers.keys()):
            providers[name].enabled = name in allow  # type: ignore[misc]
        for name in allow:
            providers.setdefault(name, ProviderProfile(enabled=True))

    elif isinstance(providers_section, dict):
        for name_raw, payload in providers_section.items():
            name = str(name_raw).strip().lower()
            if not isinstance(payload, dict):
                payload = {}
            providers[name] = _coerce_provider_profile(name, payload)

    merged = RoutingConfig(
        default_mode=str(routing.get("default_mode", DEFAULT_CONFIG.default_mode)).strip().lower() or DEFAULT_CONFIG.default_mode,
        mode_overrides=routing.get("mode_overrides", {}) if isinstance(routing.get("mode_overrides", {}), dict) else {},
        providers=providers,
        enable_cache=bool(routing.get("enable_cache", DEFAULT_CONFIG.enable_cache)),
        cache_ttl_seconds=int(routing.get("cache_ttl_seconds", DEFAULT_CONFIG.cache_ttl_seconds)),
    )

    return merged
