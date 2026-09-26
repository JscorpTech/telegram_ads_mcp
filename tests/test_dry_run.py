"""Contract tests: mutating client methods preview by default and never touch
Playwright, and the operator gates in `Settings` win over `confirm`.

The client is constructed without `__init__` (which requires an auth file), so
the dry-run branches run in isolation. Any test that reached the browser would
fail here rather than silently depending on the network.
"""

import asyncio

import pytest

from telegram_ads_mcp.client import TelegramAdsClient
from telegram_ads_mcp.exceptions import BudgetError, ReadOnlyModeError
from telegram_ads_mcp.settings import Settings


def make_client(settings: Settings | None = None) -> TelegramAdsClient:
    c = TelegramAdsClient.__new__(TelegramAdsClient)
    c._storage_state = None  # type: ignore[assignment]
    c._headless = True
    c._account_name = "Artem"
    c._p = None
    c.browser = None
    c.context = None
    c.page = None
    c._account_ready = False
    c._last_call = 0.0
    c._lock = asyncio.Lock()
    c.settings = settings or Settings()
    return c


def test_set_cpm_dry_run_default():
    result = asyncio.run(make_client().set_cpm(3, 0.25))
    assert result["dry_run"] is True
    assert result["action"] == "set_cpm"
    assert result["changes"] == {"ad_id": 3, "cpm": 0.25}


def test_set_status_dry_run_default():
    result = asyncio.run(make_client().set_status(3, "Active"))
    assert result["dry_run"] is True
    assert result["action"] == "set_status"


def test_update_ad_dry_run_default():
    result = asyncio.run(make_client().update_ad(3, title="new title"))
    assert result["dry_run"] is True
    assert result["action"] == "update_ad"
    assert result["changes"] == {"ad_id": 3, "title": "new title"}


def test_increase_budget_dry_run_default():
    result = asyncio.run(make_client().increase_budget(3, 1.0))
    assert result["dry_run"] is True
    assert result["changes"]["delta_ton"] == 1.0


def test_set_budget_dry_run_reports_target():
    result = asyncio.run(make_client().set_budget(3, 5.0))
    assert result["dry_run"] is True
    assert result["action"] == "set_budget"
    assert result["changes"] == {"target_budget": 5.0}


def test_create_ad_dry_run_default():
    result = asyncio.run(
        make_client().create_ad(
            title="t",
            text="x",
            url="t.me/bot",
            cpm=0.2,
            initial_budget=1.0,
        )
    )
    assert result["dry_run"] is True
    assert result["action"] == "create_ad"


def test_get_ad_stats_csv_dry_run_default():
    result = asyncio.run(make_client().get_ad_stats_csv(3))
    assert result["dry_run"] is True


# --------------------------------------------------------------- operator gates


def test_read_only_refuses_writes_even_when_confirmed():
    """The model cannot escalate by passing confirm=True."""
    client = make_client(Settings(read_only=True))
    for coro in (
        client.set_cpm(3, 0.25, confirm=True),
        client.set_status(3, "Active", confirm=True),
        client.increase_budget(3, 1.0, confirm=True),
        client.create_ad(
            title="t", text="x", url="t.me/b", cpm=0.2, initial_budget=1.0, confirm=True
        ),
    ):
        with pytest.raises(ReadOnlyModeError):
            asyncio.run(coro)


def test_read_only_still_allows_the_stats_download():
    """`get_ad_stats_csv` is read-only, so a monitoring deployment keeps it.

    It still needs `confirm` because it drives a real browser download, but it
    changes nothing on the account and must not be caught by the write gate.
    """
    client = make_client(Settings(read_only=True))
    result = asyncio.run(client.get_ad_stats_csv(3))
    assert result["dry_run"] is True
    assert result["action"] == "get_ad_stats_csv"


def test_spend_ceiling_blocks_large_increase():
    client = make_client(Settings(max_spend_ton=10.0))
    with pytest.raises(BudgetError):
        asyncio.run(client.increase_budget(3, 50.0, confirm=True))


def test_spend_ceiling_applies_to_previews_too():
    """A preview that could not be executed is misleading, so it is refused."""
    client = make_client(Settings(max_spend_ton=10.0))
    with pytest.raises(BudgetError):
        asyncio.run(client.increase_budget(3, 50.0))


def test_spend_ceiling_ignores_non_spend_tools():
    client = make_client(Settings(max_spend_ton=10.0))
    result = asyncio.run(client.set_status(3, "Active"))
    assert result["dry_run"] is True


def test_settings_parse_env():
    assert Settings.from_env({}).read_only is False
    assert Settings.from_env({"TELEGRAM_ADS_READ_ONLY": "1"}).read_only is True
    assert Settings.from_env({"TELEGRAM_ADS_READ_ONLY": "true"}).read_only is True
    assert Settings.from_env({"TELEGRAM_ADS_READ_ONLY": "no"}).read_only is False
    assert Settings.from_env({"TELEGRAM_ADS_MAX_SPEND_TON": "2.5"}).max_spend_ton == 2.5
    assert Settings.from_env({"TELEGRAM_ADS_MAX_SPEND_TON": "junk"}).max_spend_ton is None
    # A non-positive ceiling is meaningless, so it means "unset", not "block all".
    assert Settings.from_env({"TELEGRAM_ADS_MAX_SPEND_TON": "0"}).max_spend_ton is None
