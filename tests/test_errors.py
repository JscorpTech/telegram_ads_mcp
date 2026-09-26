"""Contract tests: domain errors carry a stable code and reach the model."""

import asyncio

import pytest

from telegram_ads_mcp import mcp_server
from telegram_ads_mcp.exceptions import (
    AccountSelectionError,
    AuthExpiredError,
    TelegramAdsError,
)


def test_codes_are_stable():
    assert AuthExpiredError.code == "AUTH_EXPIRED"
    assert AccountSelectionError.code == "ACCOUNT_SELECTION"


def test_str_includes_the_code():
    """The model only sees the string form, so the code must be in it."""
    assert str(AuthExpiredError("x")) == "AUTH_EXPIRED: x"
    assert str(AccountSelectionError()) == "ACCOUNT_SELECTION: ACCOUNT_SELECTION"


def test_default_auth_message_says_how_to_recover():
    message = str(AuthExpiredError())
    assert "telegram-ads-auth" in message


def test_subclasses_are_catchable_as_domain_errors():
    assert issubclass(AuthExpiredError, TelegramAdsError)


def test_auth_expiry_becomes_a_tool_error_not_a_crash():
    """Regression: this used to raise RuntimeError, which mcp 2.x reduces to a
    generic 'Error executing tool' string, hiding the recovery step."""
    from mcp.server.mcpserver.exceptions import ToolError

    class FailingClient:
        async def list_ads(self):
            raise AuthExpiredError()

    class Holder:
        async def get(self):
            return FailingClient()

    original = mcp_server._client
    mcp_server._client = lambda ctx: Holder()
    try:
        tool = mcp_server.mcp._tool_manager.get_tool("list_ads")
        with pytest.raises(ToolError) as excinfo:
            asyncio.run(tool.run({}, None, convert_result=True))
    finally:
        mcp_server._client = original

    text = str(excinfo.value)
    assert "AUTH_EXPIRED" in text
    assert "telegram-ads-auth" in text


def test_missing_session_file_is_a_domain_error():
    """A fresh install must get an actionable message, not a crash.

    This is also why the client is built lazily rather than in `lifespan`: an
    eager build would make a missing session a startup failure, and the server
    could never deliver this message.
    """
    from telegram_ads_mcp.client import TelegramAdsClient

    with pytest.raises(AuthExpiredError) as excinfo:
        TelegramAdsClient(storage_state="/nonexistent/auth_state.json")

    assert str(excinfo.value).startswith("AUTH_EXPIRED: ")
    assert "telegram-ads-auth" in str(excinfo.value)
