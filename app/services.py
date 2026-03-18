import asyncio
import ipaddress
import socket
from urllib.parse import urlparse
from typing import BinaryIO

import httpx
from openai import OpenAI

from .config import settings


SUPPORTED_PROVIDERS = {
    "auto",
    "mock",
    "local",
    "openai",
    "together",
    "ollama",
    "groq",
    "gemini",
    "pollinations",
    "huggingface",
}

TEXT_CAPABLE_PROVIDERS = {"mock", "local", "openai", "together", "ollama", "groq", "gemini"}
IMAGE_CAPABLE_PROVIDERS = {"mock", "local", "openai", "together", "pollinations", "huggingface"}
TRANSCRIBE_CAPABLE_PROVIDERS = {"mock", "local", "openai", "together"}


class ProviderCallError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def _together_client() -> OpenAI:
    return OpenAI(
        api_key=settings.together_api_key,
        base_url=settings.together_base_url.rstrip("/"),
    )


def _groq_client() -> OpenAI:
    return OpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url.rstrip("/"),
    )


def _provider_name() -> str:
    return settings.provider_name


def _provider_is_configured(provider: str) -> bool:
    if provider == "mock":
        return True
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider == "together":
        return bool(settings.together_api_key)
    if provider == "groq":
        return bool(settings.groq_api_key)
    if provider == "gemini":
        return bool(settings.gemini_api_key)
    if provider == "ollama":
        return bool(settings.ollama_base_url)
    if provider == "local":
        return True
    if provider == "pollinations":
        return True
    if provider == "huggingface":
        return bool(settings.huggingface_api_key)
    return False


def _candidate_providers(capability: str) -> list[str]:
    provider = _provider_name()

    if provider == "auto":
        requested = settings.provider_fallback_order_list
    else:
        requested = [provider]

    if capability == "text":
        allowed = TEXT_CAPABLE_PROVIDERS
    elif capability == "image":
        allowed = IMAGE_CAPABLE_PROVIDERS
    elif capability == "transcription":
        allowed = TRANSCRIBE_CAPABLE_PROVIDERS
    else:
        raise ValueError("Unsupported capability")

    return [p for p in requested if p in allowed]


def _run_with_fallback(capability: str, runner):
    attempts = []
    candidates = _candidate_providers(capability)

    if not candidates:
        raise ProviderCallError(
            500,
            f"No providers are configured for {capability}. Check PROVIDER and PROVIDER_FALLBACK_ORDER settings.",
        )

    for provider in candidates:
        if not _provider_is_configured(provider):
            attempts.append((provider, Exception("provider not configured")))
            continue

        try:
            return runner(provider)
        except Exception as exc:
            attempts.append((provider, exc))

    status_code = 500
    detail = "All providers failed"

    if attempts:
        last_provider, last_exc = attempts[-1]
        error_text = str(last_exc).lower()

        if all("provider not configured" in str(exc).lower() for _, exc in attempts):
            status_code = 503
            detail = (
                "AI provider credentials are not configured. "
                "Set provider API keys in environment variables."
            )
        if any(token in error_text for token in ("insufficient_quota", "quota", "billing", "payment")):
            status_code = 402
            detail = (
                f"{last_provider} provider quota/billing issue. "
                "Please top up billing or switch provider."
            )
        elif any(token in error_text for token in ("invalid api key", "incorrect api key", "unauthorized", "authentication")):
            status_code = 401
            detail = f"{last_provider} provider authentication failed. Check provider API key configuration."
        elif any(token in error_text for token in ("rate limit", "too many requests", "429")):
            status_code = 429
            detail = f"{last_provider} provider rate limit exceeded. Try again shortly."
        elif any(token in error_text for token in ("timeout", "timed out", "connection", "network")):
            status_code = 503
            detail = f"{last_provider} provider is temporarily unreachable. Please retry."

    raise ProviderCallError(status_code, detail)


# TEXT GENERATION


def _generate_text_for_provider(provider: str, prompt: str, temperature: float, max_output_tokens: int):

    if provider == "mock":
        return (f"[mock] {prompt[:200]}", "mock-text-v1", "mock")

    if provider == "local":
        return (f"[local] {prompt[:200]}", "local-v1", "local")

    if provider == "groq":
        response = _groq_client().chat.completions.create(
            model=settings.groq_text_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        text = response.choices[0].message.content
        return (text, settings.groq_text_model, "groq")

    if provider == "together":
        response = _together_client().chat.completions.create(
            model=settings.together_text_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        text = response.choices[0].message.content
        return (text, settings.together_text_model, "together")

    if provider == "openai":

        client = _client()

        response = client.chat.completions.create(
            model=settings.openai_text_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_output_tokens,
        )

        text = ""
        if response.choices:
            message = response.choices[0].message
            if message and message.content:
                text = message.content

        return (text, settings.openai_text_model, "openai")

    raise ValueError(f"Unsupported provider {provider}")


def generate_text(prompt: str, temperature: float, max_output_tokens: int):
    max_output_tokens = min(max_output_tokens, 500)

    return _run_with_fallback(
        "text",
        lambda provider: _generate_text_for_provider(provider, prompt, temperature, max_output_tokens),
    )


# IMAGE GENERATION


def _generate_image_for_provider(provider: str, prompt: str, size: str):

    if provider == "mock":
        return ("https://placehold.co/512x512", None, "mock", "mock")

    if provider == "openai":
        response = _client().images.generate(
            model=settings.openai_image_model,
            prompt=prompt,
            size=size,
        )

        image_url = None
        image_b64 = None

        if response.data:
            image_url = response.data[0].url
            image_b64 = response.data[0].b64_json

        return (image_url, image_b64, settings.openai_image_model, "openai")

    raise ValueError(f"Unsupported provider {provider}")


def generate_image(prompt: str, size: str):
    return _run_with_fallback(
        "image",
        lambda provider: _generate_image_for_provider(provider, prompt, size),
    )


# TRANSCRIPTION


def _transcribe_audio_for_provider(provider: str, file_obj: BinaryIO, filename: str, content_type: str | None):

    if provider == "mock":
        return ("mock transcription", "mock", "mock")

    if provider == "openai":
        transcript = _client().audio.transcriptions.create(
            model=settings.openai_transcription_model,
            file=(filename, file_obj, content_type or "application/octet-stream"),
        )

        return (transcript.text, settings.openai_transcription_model, "openai")

    raise ValueError(f"Unsupported provider {provider}")


def transcribe_audio(file_obj: BinaryIO, filename: str, content_type: str | None):

    def runner(provider):
        try:
            file_obj.seek(0)
        except Exception:
            pass

        return _transcribe_audio_for_provider(provider, file_obj, filename, content_type)

    return _run_with_fallback("transcription", runner)


# ============================================
# SSRF PROTECTION
# ============================================

class SSRFError(Exception):
    """Raised when a URL is suspected to be an SSRF attack."""
    pass


def _is_private_ip(ip_address: str) -> bool:
    """Check if an IP address is in a private range."""
    try:
        ip_obj = ipaddress.ip_address(ip_address)
        # Check for private IP ranges
        return (
            ip_obj.is_private or
            ip_obj.is_loopback or
            ip_obj.is_link_local or
            ip_obj.is_multicast or
            ip_obj.is_reserved or
            str(ip_obj) == "0.0.0.0"
        )
    except ValueError:
        return False


def _validate_webhook_url(url: str) -> None:
    """Validate URL for SSRF attacks."""
    
    if not url or not isinstance(url, str):
        raise SSRFError("URL must be a non-empty string")
    
    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise SSRFError("Invalid URL format")
    
    # Check scheme
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFError(f"Unsupported URL scheme: {scheme}. Only http and https allowed.")
    
    # Extract hostname
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL must specify a hostname")
    
    # Check for private IPs in hostname
    if _is_private_ip(hostname):
        raise SSRFError(f"URL hostname {hostname} is in a private IP range")
    
    # Check if hostname resolves to private IP (DNS rebinding prevention)
    if not settings.allow_private_webhook_targets:
        try:
            resolved_ips = socket.getaddrinfo(hostname, parsed.port or 80)
            for _, _, _, _, sockaddr in resolved_ips:
                ip = sockaddr[0]
                if _is_private_ip(ip):
                    raise SSRFError(
                        f"URL hostname {hostname} resolves to private IP {ip}. "
                        "Set ALLOW_PRIVATE_WEBHOOK_TARGETS=true if this is intentional."
                    )
        except socket.gaierror:
            # DNS resolution failed - could be legitimate or attack attempt. Be conservative.
            pass
        except SSRFError:
            raise
        except Exception as exc:
            # Log unexpected errors but allow the webhook
            # (e.g., network issues shouldn't block valid webhooks)
            pass


# ============================================
# AUTOMATION
# ============================================

async def run_automation_steps(steps: list[dict]):

    results = []

    timeout = httpx.Timeout(settings.default_webhook_timeout_seconds)

    async with httpx.AsyncClient(timeout=timeout) as client:

        for index, step in enumerate(steps):

            step_type = step.get("type")

            if step_type == "delay":
                await asyncio.sleep(float(step["seconds"]))

                results.append(
                    {
                        "step_index": index,
                        "type": "delay",
                        "status_code": None,
                        "detail": "delay complete",
                    }
                )
                continue

            if step_type == "webhook":
                
                webhook_url = str(step["url"])
                
                try:
                    _validate_webhook_url(webhook_url)
                except SSRFError as exc:
                    results.append(
                        {
                            "step_index": index,
                            "type": "webhook",
                            "status_code": 403,
                            "detail": f"SSRF protection: {str(exc)}",
                        }
                    )
                    continue

                try:
                    response = await client.request(
                        method=step["method"],
                        url=webhook_url,
                        headers=step.get("headers") or {},
                        json=step.get("body"),
                    )

                    results.append(
                        {
                            "step_index": index,
                            "type": "webhook",
                            "status_code": response.status_code,
                            "detail": "Webhook executed",
                        }
                    )
                except Exception as exc:
                    results.append(
                        {
                            "step_index": index,
                            "type": "webhook",
                            "status_code": 502,
                            "detail": f"Webhook request failed",
                        }
                    )
                continue

            results.append(
                {
                    "step_index": index,
                    "type": str(step_type),
                    "status_code": None,
                    "detail": "Unsupported step type",
                }
            )

    return results