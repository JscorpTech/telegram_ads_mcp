"""Tests that hit the real ads.telegram.org.

Never collected by default — they need a live session, and the default run
deselects them because `live` is an opt-in marker. They are the only tests that
can catch a change in the site's HTML, so they are worth running by hand
against a disposable account when you touch `client.py`:

    RUN_LIVE_TESTS=1 TELEGRAM_ADS_ACCOUNT=YourAccount pytest -m live -v

Requires `playwright install chromium` and a session from `telegram-ads-auth`.
Uses `asyncio.run` rather than `pytest-asyncio`, matching the rest of the
suite, so these add no dependency.
"""

import asyncio
import os

import pytest

from telegram_ads_mcp.client import TelegramAdsClient
from telegram_ads_mcp.paths import resolve_auth_state_path

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_TESTS") != "1",
        reason="set RUN_LIVE_TESTS=1 to run tests against the real site",
    ),
]


def _with_client(fn):
    """Run `fn(client)` against a real session, then close the browser."""

    async def run():
        client = TelegramAdsClient(storage_state=resolve_auth_state_path(), headless=True)
        try:
            return await fn(client)
        finally:
            await client.close()

    return asyncio.run(run())


def test_list_accounts_returns_at_least_one():
    result = _with_client(lambda c: c.list_accounts())
    assert result["accounts"], "no accounts visible to this session"
    for account in result["accounts"]:
        assert account["name"]
        assert account["token"]


def test_list_ads_shape():
    """Pins the row shape: the parsers depend on these keys existing.

    Values are not asserted — a test account may have no ads — only that each
    row is what `models.Ad` promises.
    """

    def check(c: TelegramAdsClient):
        return c.list_ads()

    result = _with_client(check)
    for ad in result["ads"]:
        assert ad["id"] is None or ad["id"] > 0
        assert isinstance(ad["views"], int)
        assert isinstance(ad["cpm"], float)
        assert isinstance(ad["budget"], float)


def test_account_budget_shape():
    result = _with_client(lambda c: c.get_account_budget())
    assert "transactions" in result
    for tx in result["transactions"]:
        assert tx["description"]
        assert isinstance(tx["amount"], float)
