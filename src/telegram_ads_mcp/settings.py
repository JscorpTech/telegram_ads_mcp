"""Environment-driven safety gates.

The `confirm` flag on each tool is a per-call decision made by the model — which
means it is not an authorization boundary: anything that can instruct the agent
can flip it. These settings are read from the environment, which the model
cannot reach, and are the actual operator-level control. The spec's own
guidance points the same way ("For trust & safety and security, there SHOULD
always be a human in the loop with the ability to deny tool invocations") and
OWASP's MCP guidance asks for least privilege and resource controls rather than
relying on the model to restrain itself.

Precedence: environment beats the tool argument. An agent cannot escalate its
own privileges by passing `confirm=True`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

READ_ONLY_ENV = "TELEGRAM_ADS_READ_ONLY"
MAX_SPEND_ENV = "TELEGRAM_ADS_MAX_SPEND_TON"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class Settings:
    """Operator-controlled limits for one server process."""

    read_only: bool = False
    """When true, state-changing tools are refused before any I/O.

    Read-only tools still work, so the server stays useful for monitoring while
    the spend surface is removed entirely.
    """

    max_spend_ton: float | None = None
    """Ceiling on a single budget-increasing call, in TON.

    Applies to `increase_budget`, `set_budget`, and the `initial_budget` of
    `create_ad`. `None` means no ceiling.
    """

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        return cls(
            read_only=(env.get(READ_ONLY_ENV, "").strip().lower() in _TRUTHY),
            max_spend_ton=_parse_positive_float(env.get(MAX_SPEND_ENV)),
        )

    def check_can_write(self, action: str) -> None:
        """Reject a state-changing action while read-only mode is on."""
        if self.read_only:
            from telegram_ads_mcp.exceptions import ReadOnlyModeError

            raise ReadOnlyModeError(
                f"`{action}` is disabled because {READ_ONLY_ENV} is set. "
                f"Unset it and restart the server to allow changes."
            )

    def check_spend(self, amount: float, action: str) -> None:
        """Reject a budget increase that exceeds the configured ceiling."""
        if self.max_spend_ton is None:
            return
        if amount > self.max_spend_ton:
            from telegram_ads_mcp.exceptions import BudgetError

            raise BudgetError(
                f"`{action}` would spend {amount} TON, above the "
                f"{self.max_spend_ton} TON ceiling set by {MAX_SPEND_ENV}."
            )


def _parse_positive_float(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None
