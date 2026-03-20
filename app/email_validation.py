from __future__ import annotations

import re
from dataclasses import dataclass


EMAIL_REGEX = re.compile(
    r"^(?=.{1,254}$)(?=.{1,64}@)[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)


@dataclass(frozen=True)
class EmailValidationResult:
    is_valid: bool
    normalized_email: str | None
    error: str | None = None


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _is_blocked_domain(domain: str, blocked_domains: set[str]) -> bool:
    return domain in blocked_domains or any(domain.endswith(f".{blocked}") for blocked in blocked_domains)


def validate_email_address(value: str | None, blocked_domains: set[str] | None = None) -> EmailValidationResult:
    normalized = normalize_email(value)
    if not normalized:
        return EmailValidationResult(False, None, "Email is required.")

    if normalized.count("@") != 1:
        return EmailValidationResult(False, None, "Email format is invalid.")

    if not EMAIL_REGEX.fullmatch(normalized):
        return EmailValidationResult(False, None, "Email format is invalid.")

    _, domain = normalized.rsplit("@", 1)
    blocked = {item.strip().lower() for item in (blocked_domains or set()) if item and item.strip()}
    if _is_blocked_domain(domain, blocked):
        return EmailValidationResult(False, None, f"Email domain '{domain}' is blocked.")

    return EmailValidationResult(True, normalized, None)
