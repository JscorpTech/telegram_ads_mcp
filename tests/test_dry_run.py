"""Contract tests: mutating client methods must return dry-run previews by default,
without touching Playwright/the browser, when confirm is not passed.
"""

import asyncio

from telegram_ads_mcp.client import TelegramAdsClient


def make_client() -> TelegramAdsClient:
    """Construct a client without running __init__ (which requires an auth file
    and never touches the browser), so dry-run branches can be exercised in
    isolation.
    """
    c = TelegramAdsClient.__new__(TelegramAdsClient)
    c._storage_state = None  # type: ignore[assignment]
    c._headless = True
    c._account_name = "Artem"
    c._p = None
    c.browser = None
    c.context = None
    c.page = None
    c._account_ready = False
    c._lock = asyncio.Lock()
    return c


def test_set_cpm_dry_run_default():
    c = make_client()
    result = asyncio.run(c.set_cpm(3, 0.25))
    assert result["dry_run"] is True
    assert result["action"] == "set_cpm"
    assert result["cpm"] == 0.25


def test_set_status_dry_run_default():
    c = make_client()
    result = asyncio.run(c.set_status(3, "Active"))
    assert result["dry_run"] is True
    assert result["action"] == "set_status"


def test_update_ad_dry_run_default():
    c = make_client()
    result = asyncio.run(c.update_ad(3, title="new title"))
    assert result["dry_run"] is True
    assert result["action"] == "update_ad"


def test_increase_budget_dry_run_default():
    c = make_client()
    result = asyncio.run(c.increase_budget(3, 1.0))
    assert result["dry_run"] is True
    assert result["delta_ton"] == 1.0


def test_set_budget_dry_run_default():
    c = make_client()
    result = asyncio.run(c.set_budget(3, 5.0))
    assert result["dry_run"] is True
    assert result["action"] == "set_budget"
    assert result["target_budget"] == 5.0


def test_create_ad_dry_run_default():
    c = make_client()
    result = asyncio.run(
        c.create_ad(
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
    c = make_client()
    result = asyncio.run(c.get_ad_stats_csv(3))
    assert isinstance(result, dict)
    assert result["dry_run"] is True
