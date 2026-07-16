"""Shared exceptions for Telegram Ads client."""

from __future__ import annotations


class AuthExpiredError(Exception):
    """Raised when stored session is no longer valid."""

    code = "AUTH_EXPIRED"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)
