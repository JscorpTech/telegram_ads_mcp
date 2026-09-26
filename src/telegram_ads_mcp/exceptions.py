"""Domain errors raised by the Telegram Ads client.

These are plain exceptions, deliberately independent of the MCP SDK: `client`
is usable as a library without importing `mcp`. The translation into MCP wire
semantics happens in `mcp_server` — an anticipated failure becomes a *tool
execution error* (`isError: true`, message preserved for the model to act on),
per spec revision 2026-07-28, "Error Handling".

Every error carries a stable `code` so agents and scripts can branch on the
cause instead of matching prose.
"""

from __future__ import annotations


class TelegramAdsError(Exception):
    """Base class for anticipated Telegram Ads failures."""

    code = "TELEGRAM_ADS_ERROR"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.code
        super().__init__(self.message)

    def __str__(self) -> str:
        """Render as `<CODE>: <message>` so the code survives into tool output.

        The model sees only the string form of the error, so the code has to be
        part of it; the class alone is not visible over the wire.
        """
        return f"{self.code}: {self.message}"


class AuthExpiredError(TelegramAdsError):
    """Raised when the stored session is missing, unreadable, or no longer valid.

    Recovering means running `telegram-ads-auth`, so this must reach the model
    as actionable text rather than a generic crash. Covers both "no session
    file yet" and "the site rejected the session": the fix is the same, and
    distinguishing them only matters in the message.
    """

    code = "AUTH_EXPIRED"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "The saved Telegram Ads session is missing or no longer valid. "
            "Run `telegram-ads-auth` to create or refresh it."
        )


class AccountSelectionError(TelegramAdsError):
    """Raised when no single account can be selected from the login."""

    code = "ACCOUNT_SELECTION"


class BudgetError(TelegramAdsError):
    """Raised when a budget change is impossible or nonsensical."""

    code = "BUDGET"


class ReadOnlyModeError(TelegramAdsError):
    """Raised when a state-changing tool is called while read-only mode is on."""

    code = "READ_ONLY"
