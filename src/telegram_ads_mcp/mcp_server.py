#!/usr/bin/env python3
"""MCP server exposing Telegram Ads operations."""

from __future__ import annotations

import asyncio
import atexit
import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from telegram_ads_mcp.client import (
    AdStatus,
    Currency,
    StatsPeriod,
    TargetType,
    TelegramAdsClient,
)
from telegram_ads_mcp.exceptions import AuthExpiredError
from telegram_ads_mcp.paths import resolve_auth_state_path

mcp = FastMCP("telegram-ads")

# Annotation profiles per Design §2 (tool surface and safety table).
# readOnlyHint/destructiveHint/openWorldHint are UX hints for MCP clients,
# not a security boundary; the confirm=True gate is the actual boundary.
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
SPEND = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)

_client: TelegramAdsClient | None = None
_client_lock = asyncio.Lock()


async def _get_client() -> TelegramAdsClient:
    global _client
    async with _client_lock:
        if _client is None:
            _client = TelegramAdsClient(
                storage_state=resolve_auth_state_path(), headless=True
            )
        return _client


def _shutdown() -> None:
    global _client
    if _client is not None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_client.close())
            else:
                loop.run_until_complete(_client.close())
        except Exception:  # noqa: BLE001, S110 - best-effort atexit cleanup
            pass
        _client = None


atexit.register(_shutdown)


def _handle(result: Any) -> Any:
    if isinstance(result, bytes):
        return result.decode("utf-8", errors="replace")
    return result


@mcp.tool(annotations=READ)
async def list_accounts() -> list[dict]:
    """List Telegram Ads accounts available for this login session."""
    try:
        return await (await _get_client()).list_accounts()
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=READ)
async def list_ads() -> list[dict]:
    """List all ads with full table columns (id, metrics, budget, status, date)."""
    try:
        return await (await _get_client()).list_ads()
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=READ)
async def get_ad_info(ad_id: int) -> dict:
    """Read ad form fields. Targeting chips are read-only for existing ads."""
    try:
        return await (await _get_client()).get_ad_info(ad_id)
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=WRITE)
async def update_ad(
    ad_id: int,
    title: str | None = None,
    text: str | None = None,
    url: str | None = None,
    website_name: str | None = None,
    show_bot_picture: bool | None = None,
    daily_budget: float | None = None,
    daily_views_limit: int | None = None,
    status: AdStatus | None = None,
    confirm: bool = False,
) -> dict:
    """Update ad info fields (not CPM/budget). Requires confirm=True to save; default is dry-run."""
    try:
        return await (await _get_client()).update_ad(
            ad_id,
            title=title,
            text=text,
            url=url,
            website_name=website_name,
            show_bot_picture=show_bot_picture,
            daily_budget=daily_budget,
            daily_views_limit=daily_views_limit,
            status=status,
            confirm=confirm,
        )
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=WRITE)
async def set_cpm(ad_id: int, cpm: float, confirm: bool = False) -> dict:
    """Set CPM via /edit_cpm modal. Requires confirm=True to execute; default is dry-run."""
    try:
        return await (await _get_client()).set_cpm(ad_id, cpm, confirm=confirm)
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=WRITE)
async def set_status(ad_id: int, status: AdStatus, confirm: bool = False) -> dict:
    """Set ad status (Active / On Hold) via /edit_status modal. Requires confirm=True to execute; default is dry-run."""
    try:
        return await (await _get_client()).set_status(ad_id, status, confirm=confirm)
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=SPEND)
async def increase_budget(ad_id: int, amount: float, confirm: bool = False) -> dict:
    """Add an amount in the selected cabinet currency to ad budget (delta). Financial — requires confirm=True to execute; default is dry-run."""
    try:
        return await (await _get_client()).increase_budget(
            ad_id, amount, confirm=confirm
        )
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=SPEND)
async def set_budget(ad_id: int, target_budget: float, confirm: bool = False) -> dict:
    """Set target budget by computing delta from current. Financial — requires confirm=True to execute; default is dry-run."""
    try:
        return await (await _get_client()).set_budget(
            ad_id, target_budget, confirm=confirm
        )
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=WRITE)
async def get_ad_stats_csv(
    ad_id: int, period: StatsPeriod = "days", confirm: bool = False
) -> str:
    """Download stats CSV. Requires confirm=True to actually download; default is dry-run."""
    try:
        result = await (await _get_client()).get_ad_stats_csv(
            ad_id, period=period, confirm=confirm
        )
        if isinstance(result, dict):
            return json.dumps(result)
        return _handle(result)
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=WRITE)
async def create_ad(
    title: str,
    text: str,
    url: str,
    cpm: float,
    initial_budget: float,
    target_type: TargetType = "channels",
    targets: list[str] | None = None,
    website_name: str | None = None,
    show_bot_picture: bool = False,
    daily_views_limit: int = 4,
    status: AdStatus = "Active",
    clear_draft: bool = True,
    confirm: bool = False,
    currency: Currency | None = None,
) -> dict:
    """Create ad in cabinet currency (EUR or TON), without conversion. Pass currency to reject a mismatch before editing. Financial: confirm=True required; default is dry-run."""
    try:
        return await (await _get_client()).create_ad(
            title=title,
            text=text,
            url=url,
            cpm=cpm,
            initial_budget=initial_budget,
            currency=currency,
            target_type=target_type,
            targets=targets,
            website_name=website_name,
            show_bot_picture=show_bot_picture,
            daily_views_limit=daily_views_limit,
            status=status,
            clear_draft=clear_draft,
            confirm=confirm,
        )
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=READ)
async def get_account_budget() -> dict:
    """Read-only: per-ad budgets on /account/budget. Fragment top-up is manual."""
    try:
        return await (await _get_client()).get_account_budget()
    except AuthExpiredError as e:
        raise RuntimeError(str(e)) from e


@mcp.tool(annotations=READ)
async def get_create_ad_form() -> dict:
    """Read cabinet currency and validate creation money fields; no draft edits or spending."""
    return await (await _get_client()).get_create_ad_form()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
