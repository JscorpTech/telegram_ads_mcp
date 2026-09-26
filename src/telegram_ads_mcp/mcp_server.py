#!/usr/bin/env python3
"""MCP server exposing Telegram Ads operations.

Written against MCP Python SDK 2.x (`MCPServer`, formerly `FastMCP`) and spec
revision 2026-07-28. Two SDK behaviours shape this file:

* An *anticipated* failure must raise `ToolError`, which the SDK turns into a
  tool execution error (`isError: true`) whose message the model can read and
  act on. Any other exception is treated as a crash and reduced to a generic
  "Error executing tool" string, so domain errors are translated at the
  boundary rather than escaping.
* A tool's return annotation is what publishes its `outputSchema` and fills in
  `structuredContent`, so every tool returns a TypedDict from `models`.

Safety is layered deliberately: the `confirm` flag is the model's per-call
decision, while `Settings` (read-only mode, spend ceiling) comes from the
environment and cannot be reached by anything that can talk to the model.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from telegram_ads_mcp import __version__
from telegram_ads_mcp.client import TelegramAdsClient
from telegram_ads_mcp.exceptions import TelegramAdsError
from telegram_ads_mcp.models import (
    AccountBudget,
    AccountList,
    ActionResult,
    AdInfo,
    AdList,
    AdStatus,
    StatsCsv,
    StatsPeriod,
    TargetType,
)
from telegram_ads_mcp.paths import resolve_auth_state_path
from telegram_ads_mcp.settings import Settings

# Annotation profiles. Per spec revision 2026-07-28 these are *untrusted hints*
# that clients may use for consent UX — never a security boundary. The real
# boundary is the `confirm` gate plus `Settings`. Read-only is stated
# affirmatively; `destructive_hint` defaults to true when unset, so additive
# tools must say so explicitly, and repeating a state-setting call is safe
# (`idempotent_hint=True`) whereas adding budget is not.
#
# Constructed with snake_case: the SDK accepts camelCase aliases too, but only
# snake_case is introspectable, and the camelCase spelling fails type checking.
READ = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
)
SPEND = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True
)

INSTRUCTIONS = """
Read and manage Telegram Ads campaigns for one account, by driving the real
ads.telegram.org web UI through a saved browser session.

Tools that change anything default to `confirm=false`, which returns a preview
of exactly what would happen and touches nothing. Pass `confirm=true` to
execute. Budget-increasing tools spend TON; the operator may additionally cap
them with `TELEGRAM_ADS_MAX_SPEND_TON` or disable all changes with
`TELEGRAM_ADS_READ_ONLY=1`.

If a tool reports `AUTH_EXPIRED`, the saved session is no longer valid — ask
the user to run `telegram-ads-auth` and restart the server.
""".strip()


def _as_tool_error(exc: TelegramAdsError) -> ToolError:
    """Translate a domain error into the SDK's anticipated-failure channel.

    `str(exc)` renders as `<CODE>: <message>`, so the code survives to the
    model and it can tell "re-authenticate" from "you passed a bad number".
    """
    return ToolError(str(exc))


class ClientHolder:
    """Lazily builds the client and closes it at shutdown.

    Construction is deferred to the first tool call rather than done in
    `lifespan`. Building eagerly would make a missing or stale `auth_state.json`
    a startup failure: the server would die before it could tell the model to
    run `telegram-ads-auth`, and the client would report a protocol error
    instead of an actionable tool error.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings
        self._client: TelegramAdsClient | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> TelegramAdsClient:
        async with self._lock:
            if self._client is None:
                self._client = TelegramAdsClient(
                    storage_state=resolve_auth_state_path(),
                    headless=True,
                    settings=self._settings or Settings.from_env(),
                )
            return self._client

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.close()


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[ClientHolder]:
    """Provide one client per server process and close it deterministically.

    Replaces the previous module-level singleton plus `atexit` hook: under
    `mcp.run()` the interpreter exits inside `anyio.run`, where there is no
    current event loop, so the old `atexit` handler silently did nothing and
    leaked a Chromium process on every exit.
    """
    holder = ClientHolder()
    try:
        yield holder
    finally:
        await holder.close()


mcp = MCPServer(
    "telegram-ads",
    version=__version__,
    instructions=INSTRUCTIONS,
    lifespan=lifespan,
)


def _client(ctx: Context) -> ClientHolder:
    """Return the lifespan-scoped client holder for this request.

    The SDK injects a `Context` whose lifespan slot it types as `dict[str, Any]`
    because it cannot see through `mcp = MCPServer(..., lifespan=lifespan)`. The
    runtime value is what `lifespan` yielded, so the cast states what the wiring
    already guarantees rather than widening the return type and losing checking
    at every call site.
    """
    return cast(ClientHolder, ctx.request_context.lifespan_context)


# --------------------------------------------------------------------- read tools


@mcp.tool(annotations=READ, title="List Telegram Ads Accounts")
async def list_accounts(ctx: Context) -> AccountList:
    """List the Telegram Ads accounts available to the saved login session.

    Use this first when `TELEGRAM_ADS_ACCOUNT` is unset or an account-scoped
    tool reports an account-selection error.
    """
    try:
        return await (await _client(ctx).get()).list_accounts()
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


@mcp.tool(annotations=READ, title="List Ads")
async def list_ads(ctx: Context) -> AdList:
    """List every ad on the account with its full metrics table.

    Each row carries id, title, promo URL, the view/click/action counters, the
    cost metrics (cpm, cpc, cpa, spent), budget, target, status and date added.
    Use this to find an `ad_id` for the other tools.
    """
    try:
        return await (await _client(ctx).get()).list_ads()
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


@mcp.tool(annotations=READ, title="Get Ad Details")
async def get_ad_info(
    ctx: Context,
    ad_id: Annotated[int, Field(gt=0, description="Ad id from `list_ads`")],
) -> AdInfo:
    """Read one ad's editable form fields and its current settings.

    Targeting is read-only here: `targets` and `excluded_countries` are shown
    for context, but changing them on an existing ad is not supported.
    """
    try:
        return await (await _client(ctx).get()).get_ad_info(ad_id)
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


@mcp.tool(annotations=READ, title="Get Account Budget")
async def get_account_budget(ctx: Context) -> AccountBudget:
    """Read the account budget: current balance and the transaction ledger.

    Read-only. Topping up requires Fragment and is not automated; the response
    includes the Fragment URL for the user to open.
    """
    try:
        return await (await _client(ctx).get()).get_account_budget()
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


# -------------------------------------------------------------------- write tools


@mcp.tool(annotations=WRITE, title="Update Ad")
async def update_ad(
    ctx: Context,
    ad_id: Annotated[int, Field(gt=0, description="Ad id from `list_ads`")],
    title: Annotated[str | None, Field(description="New ad title")] = None,
    text: Annotated[str | None, Field(description="New ad body text")] = None,
    url: Annotated[
        str | None, Field(description="Promoted channel/post/bot URL (t.me/...)")
    ] = None,
    website_name: Annotated[str | None, Field(description="Name of the promoted website")] = None,
    show_bot_picture: Annotated[
        bool | None, Field(description="Show the bot's picture on the ad")
    ] = None,
    daily_budget: Annotated[
        float | None, Field(gt=0, description="Daily spend limit in TON")
    ] = None,
    daily_views_limit: Annotated[
        int | None, Field(description="Max views per user, e.g. 1, 2 or 4")
    ] = None,
    status: Annotated[AdStatus | None, Field(description="Set the ad Active or On Hold")] = None,
    confirm: Annotated[
        bool, Field(description="false (default) previews; true saves for real")
    ] = False,
) -> ActionResult:
    """Update an existing ad's info fields.

    Only the fields you pass are changed. This does not set CPM (see `set_cpm`)
    or add budget (see `increase_budget`). Preview by default.
    """
    try:
        return await (await _client(ctx).get()).update_ad(
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
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


@mcp.tool(annotations=WRITE, title="Set CPM")
async def set_cpm(
    ctx: Context,
    ad_id: Annotated[int, Field(gt=0, description="Ad id from `list_ads`")],
    cpm: Annotated[float, Field(gt=0, description="New CPM in TON")],
    confirm: Annotated[
        bool, Field(description="false (default) previews; true saves for real")
    ] = False,
) -> ActionResult:
    """Set an ad's CPM through the `/edit_cpm` modal. Preview by default."""
    try:
        return await (await _client(ctx).get()).set_cpm(ad_id, cpm, confirm=confirm)
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


@mcp.tool(annotations=WRITE, title="Set Ad Status")
async def set_status(
    ctx: Context,
    ad_id: Annotated[int, Field(gt=0, description="Ad id from `list_ads`")],
    status: Annotated[AdStatus, Field(description="Target status: Active or On Hold")],
    confirm: Annotated[
        bool, Field(description="false (default) previews; true saves for real")
    ] = False,
) -> ActionResult:
    """Set an ad's status to Active or On Hold. Preview by default."""
    try:
        return await (await _client(ctx).get()).set_status(ad_id, status, confirm=confirm)
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


@mcp.tool(annotations=SPEND, title="Increase Ad Budget")
async def increase_budget(
    ctx: Context,
    ad_id: Annotated[int, Field(gt=0, description="Ad id from `list_ads`")],
    amount: Annotated[float, Field(gt=0, description="TON to add to the existing budget")],
    confirm: Annotated[
        bool, Field(description="false (default) previews; true spends for real")
    ] = False,
) -> ActionResult:
    """Add TON to an ad's budget.

    This spends real money and cannot be undone from this server. Preview by
    default; check the preview, then re-call with `confirm=true`.
    """
    try:
        return await (await _client(ctx).get()).increase_budget(ad_id, amount, confirm=confirm)
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


@mcp.tool(annotations=SPEND, title="Set Ad Budget")
async def set_budget(
    ctx: Context,
    ad_id: Annotated[int, Field(gt=0, description="Ad id from `list_ads`")],
    target_budget: Annotated[float, Field(gt=0, description="Desired total budget in TON")],
    confirm: Annotated[
        bool, Field(description="false (default) previews; true spends for real")
    ] = False,
) -> ActionResult:
    """Set an ad's total budget, adding the difference to what it already has.

    The delta is read from the live account, so it is only computed when
    `confirm=true`; the default preview reports the target instead. Spends real
    money.
    """
    try:
        return await (await _client(ctx).get()).set_budget(ad_id, target_budget, confirm=confirm)
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


@mcp.tool(annotations=SPEND, title="Create Ad")
async def create_ad(
    ctx: Context,
    title: Annotated[str, Field(min_length=1, description="Ad title")],
    text: Annotated[str, Field(min_length=1, description="Ad body text")],
    url: Annotated[str, Field(min_length=1, description="Promoted t.me URL")],
    cpm: Annotated[float, Field(gt=0, description="Starting CPM in TON")],
    initial_budget: Annotated[
        float, Field(gt=0, description="Initial budget in TON (spends real money)")
    ],
    target_type: Annotated[
        TargetType, Field(description="Targeting kind: channels, bots or search")
    ] = "channels",
    targets: Annotated[
        list[str] | None,
        Field(description="Target channels/bots/queries, matching `target_type`"),
    ] = None,
    website_name: Annotated[str | None, Field(description="Name of the promoted website")] = None,
    show_bot_picture: Annotated[
        bool, Field(description="Show the bot's picture on the ad")
    ] = False,
    daily_views_limit: Annotated[int, Field(description="Max views per user, e.g. 1, 2 or 4")] = 4,
    status: Annotated[AdStatus, Field(description="Initial status")] = "Active",
    clear_draft: Annotated[
        bool, Field(description="Discard any existing draft before creating")
    ] = True,
    confirm: Annotated[
        bool, Field(description="false (default) previews; true creates for real")
    ] = False,
) -> ActionResult:
    """Create a new ad and fund it with the initial budget.

    This spends real money. Drafts are cleared first unless `clear_draft=false`.
    Preview by default.
    """
    try:
        return await (await _client(ctx).get()).create_ad(
            title=title,
            text=text,
            url=url,
            cpm=cpm,
            initial_budget=initial_budget,
            target_type=target_type,
            targets=targets,
            website_name=website_name,
            show_bot_picture=show_bot_picture,
            daily_views_limit=daily_views_limit,
            status=status,
            clear_draft=clear_draft,
            confirm=confirm,
        )
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


@mcp.tool(annotations=READ, title="Download Ad Stats CSV")
async def get_ad_stats_csv(
    ctx: Context,
    ad_id: Annotated[int, Field(gt=0, description="Ad id from `list_ads`")],
    period: Annotated[
        StatsPeriod, Field(description="Stats granularity: day/days, or 5min")
    ] = "days",
    confirm: Annotated[bool, Field(description="false (default) previews; true downloads")] = False,
) -> StatsCsv | ActionResult:
    """Download an ad's performance stats as CSV text.

    Annotated read-only because it changes nothing on the account, but it does
    drive a real browser download, so it still needs `confirm=true`. Large
    exports are truncated with an explicit marker.
    """
    try:
        return await (await _client(ctx).get()).get_ad_stats_csv(
            ad_id, period=period, confirm=confirm
        )
    except TelegramAdsError as exc:
        raise _as_tool_error(exc) from exc


def main() -> None:
    """Run the server over stdio.

    Stdio is the right transport here and also the safer one: the spec tells
    stdio servers to take credentials from the environment (which this does via
    `TELEGRAM_ADS_AUTH_STATE`) rather than running an authorization flow, and
    it means the process never binds a network port.
    """
    mcp.run()


if __name__ == "__main__":
    main()
