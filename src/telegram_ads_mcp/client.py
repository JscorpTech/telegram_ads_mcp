"""Async Playwright client for ads.telegram.org (server-rendered HTML forms).

This layer knows nothing about MCP: it takes plain arguments and returns the
TypedDicts in `models`. Keeping it SDK-free means it can be used and tested as
an ordinary library, and it keeps the wire concerns in `mcp_server`.

Every page it reads is remote, attacker-influenced content, and every mutation
it performs spends real money. The `confirm` / `Settings` gates are enforced
here, closest to the browser, so that no tool wrapper can forget them.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any, cast

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)

from telegram_ads_mcp.exceptions import (
    AccountSelectionError,
    AuthExpiredError,
    BudgetError,
    TelegramAdsError,
)
from telegram_ads_mcp.models import (
    Account,
    AccountBudget,
    AccountList,
    ActionResult,
    Ad,
    AdInfo,
    AdList,
    AdStatus,
    StatsCsv,
    StatsPeriod,
    Target,
    TargetType,
    Transaction,
)
from telegram_ads_mcp.parsing import _AD_ID_RE, extract_ad_id, parse_decimal, parse_int_commas
from telegram_ads_mcp.paths import ensure_secure_file, resolve_auth_state_path
from telegram_ads_mcp.settings import Settings

BASE = "https://ads.telegram.org"
DEFAULT_AUTH_STATE = resolve_auth_state_path()

# Minimum spacing between two browser-driving calls, in seconds. The spec asks
# servers to rate limit tool invocations, and an agent loop that hammers
# ads.telegram.org risks getting the account throttled or flagged. Calls are
# already serialised by `self._lock`; this adds a floor to the spacing.
MIN_SECONDS_BETWEEN_CALLS = 0.25

# Cap on a downloaded stats CSV, in characters. The CSV is remote content on
# its way into a model's context, so it is bounded rather than trusted to be
# small; the truncation is reported in the payload, never silent.
MAX_CSV_CHARS = 200_000

# Which actions move TON, and which key in their `changes` carries the amount.
# Used by `_dry_or_run` to apply the `TELEGRAM_ADS_MAX_SPEND_TON` ceiling to
# real calls and previews alike.
_SPEND_ACTIONS: dict[str, str] = {
    "increase_budget": "delta_ton",
    "set_budget": "delta_ton",
    "create_ad": "initial_budget",
}


def _spend_amount(action: str, changes: dict[str, Any]) -> float | None:
    key = _SPEND_ACTIONS.get(action)
    if key is None:
        return None
    value = changes.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def choose_account(accounts: list[Account], preferred_name: str | None) -> Account:
    """Pick an account by substring match, or auto-select when unambiguous."""
    if not accounts:
        raise AccountSelectionError("No accounts available")

    if preferred_name:
        needle = preferred_name.lower()
        match = next(
            (a for a in accounts if needle in a["name"].lower()),
            None,
        )
        if match is None:
            names = ", ".join(a["name"] for a in accounts)
            raise AccountSelectionError(f"Account '{preferred_name}' not found. Available: {names}")
        return match

    if len(accounts) == 1:
        return accounts[0]

    names = ", ".join(a["name"] for a in accounts)
    raise AccountSelectionError(f"TELEGRAM_ADS_ACCOUNT is not set. Set it to one of: {names}")


class TelegramAdsClient:
    def __init__(
        self,
        storage_state: str | Path = DEFAULT_AUTH_STATE,
        headless: bool = True,
        account_name: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._storage_state = Path(storage_state)
        if not self._storage_state.exists():
            raise AuthExpiredError(
                f"No saved session at {self._storage_state}. Run `telegram-ads-auth` to create one."
            )
        self._headless = headless
        self._account_name = account_name or os.environ.get("TELEGRAM_ADS_ACCOUNT")
        self.settings = settings or Settings.from_env()
        self._p: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._account_ready = False
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ lifecycle

    async def _throttle(self) -> None:
        """Space out browser calls so an agent loop cannot hammer the site."""
        elapsed = time.monotonic() - self._last_call
        if elapsed < MIN_SECONDS_BETWEEN_CALLS:
            await asyncio.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
        self._last_call = time.monotonic()

    async def _ensure_started(self) -> Page:
        if self.page is not None:
            return self.page
        self._p = await async_playwright().start()
        self.browser = await self._p.chromium.launch(headless=self._headless)
        self.context = await self.browser.new_context(storage_state=str(self._storage_state))
        self.page = await self.context.new_page()
        return self.page

    async def close(self) -> None:
        """Tear down the browser. Safe to call more than once."""
        try:
            if self.browser:
                await self.browser.close()
        finally:
            if self._p:
                await self._p.stop()
            self.page = None
            self.context = None
            self.browser = None
            self._p = None
            self._account_ready = False

    async def __aenter__(self) -> TelegramAdsClient:
        await self._ensure_started()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ------------------------------------------------------------------ navigation

    async def _dismiss_ad_blocker(self, page: Page) -> None:
        blocker = page.locator("text=Turn off ad blocker")
        if await blocker.count() > 0 and await blocker.first.is_visible():
            close = page.get_by_role("button", name="Close")
            if await close.count() > 0:
                await close.first.click()

    async def _check_auth(self, page: Page) -> None:
        url = page.url
        if "ads.telegram.org" not in url:
            raise AuthExpiredError()
        for text in ("Log in with Telegram", "Login with Telegram"):
            marker = page.get_by_text(text, exact=False)
            if await marker.count() > 0 and await marker.first.is_visible():
                raise AuthExpiredError()

    async def list_accounts(self) -> AccountList:
        async with self._lock:
            await self._throttle()
            return AccountList(accounts=await self._list_accounts_unlocked())

    async def _list_accounts_unlocked(self) -> list[Account]:
        page = await self._ensure_started()
        await page.goto(f"{BASE}/choose_account?to=account", wait_until="domcontentloaded")
        await self._check_auth(page)
        accounts: list[Account] = []
        for link in await page.locator("a[href^='/choose_account/']").all():
            href = await link.get_attribute("href") or ""
            if href.endswith("/new"):
                continue
            text = (await link.inner_text()).strip().replace("\n", " ")
            token = href.rsplit("/", 1)[-1]
            accounts.append(Account(name=text, token=token, href=href))
        seen: set[str] = set()
        unique: list[Account] = []
        for acc in accounts:
            if acc["token"] in seen:
                continue
            seen.add(acc["token"])
            unique.append(acc)
        return unique

    async def _ensure_account(self, page: Page) -> None:
        if self._account_ready and "/choose_account" not in page.url:
            return
        if "/choose_account" not in page.url:
            # Probe whether account is already selected
            await page.goto(f"{BASE}/account", wait_until="domcontentloaded")
            await self._dismiss_ad_blocker(page)
            await self._check_auth(page)
            if "/choose_account" not in page.url:
                self._account_ready = True
                return

        accounts = await self._list_accounts_unlocked()
        if not accounts:
            raise AuthExpiredError("No accounts available — session may be expired")

        match = choose_account(accounts, self._account_name)

        await page.goto(f"{BASE}{match['href']}", wait_until="domcontentloaded")
        await self._dismiss_ad_blocker(page)
        await self._check_auth(page)
        if (
            "/choose_account" in page.url
            and "Please complete" in await page.locator("body").inner_text()
        ):
            raise TelegramAdsError(
                f"Account '{match['name']}' requires profile completion before use"
            )
        # Persist refreshed cookies only once the login actually resolved to
        # one account, so a half-authenticated page is never written to disk.
        if self.context:
            await self.context.storage_state(path=str(self._storage_state))
            ensure_secure_file(self._storage_state)
        self._account_ready = True

    async def _goto(self, path: str) -> Page:
        page = await self._ensure_started()
        await self._ensure_account(page)
        await page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
        await self._dismiss_ad_blocker(page)
        await self._check_auth(page)
        if "/choose_account" in page.url:
            self._account_ready = False
            await self._ensure_account(page)
            await page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
            await self._dismiss_ad_blocker(page)
            await self._check_auth(page)
        # Surface site 404s clearly
        body = await page.locator("body").inner_text()
        if "404 Not Found" in body or page.url.endswith("/404"):
            raise TelegramAdsError(f"404 Not Found for {path} (url={page.url})")
        return page

    def _dry_or_run(
        self,
        action: str,
        changes: dict[str, Any],
        *,
        confirm: bool,
        mutates: bool = True,
    ) -> ActionResult | None:
        """Return a preview unless `confirm`, after applying the operator gates.

        The gates run first and unconditionally: `TELEGRAM_ADS_READ_ONLY`
        refuses a mutating call whether or not the model passed `confirm=True`.

        `mutates=False` is for actions that only read the account but still need
        the preview/confirm round trip because they drive a browser download —
        `get_ad_stats_csv`. Those stay available in read-only mode, so a
        monitoring-only deployment can still pull stats.
        """
        if mutates:
            self.settings.check_can_write(action)
            if _SPEND_ACTIONS.get(action):
                amount = _spend_amount(action, changes)
                if amount is not None:
                    self.settings.check_spend(amount, action)
        if not confirm:
            return ActionResult(action=action, dry_run=True, changes=changes)
        return None

    @staticmethod
    def _result(
        action: str,
        *,
        ad_id: int | None = None,
        changes: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ) -> ActionResult:
        result = ActionResult(action=action, dry_run=False)
        if ad_id is not None:
            result["ad_id"] = ad_id
        if changes:
            result["changes"] = changes
        if errors:
            result["errors"] = errors
        return result

    async def _read_validation_errors(self, page: Page) -> list[str]:
        errors: list[str] = []
        for selector in (".error", "[class*='invalid']", "[class*='error']"):
            loc = page.locator(selector)
            for i in range(await loc.count()):
                text = (await loc.nth(i).inner_text()).strip()
                if text:
                    errors.append(text)
        return errors

    async def _read_targets(self, page: Page) -> list[Target]:
        """Targets live in the first .pr-form-info-block (channels/bots/queries)."""
        block = page.locator(".pr-form-info-block").first
        if await block.count() == 0:
            return []
        targets: list[Target] = []
        for el in await block.locator("a.value, span.value").all():
            text = (await el.inner_text()).strip()
            if not text:
                continue
            href = await el.get_attribute("href")
            item = Target(name=text)
            if href:
                item["url"] = href
            targets.append(item)
        return targets

    async def _read_excluded_countries(self, page: Page) -> list[str]:
        blocks = page.locator(".pr-form-info-block")
        if await blocks.count() < 2:
            return []
        block = blocks.nth(1)
        return [
            (await el.inner_text()).strip()
            for el in await block.locator("span.value").all()
            if (await el.inner_text()).strip()
        ]

    async def _extract_ad_id_from_row(self, row: Locator) -> int | None:
        for link in await row.locator("a[href*='/account/ad/']").all():
            ad_id = extract_ad_id(await link.get_attribute("href"))
            if ad_id is not None:
                return ad_id
        return None

    # ------------------------------------------------------------------ list_ads

    async def list_ads(self) -> AdList:
        async with self._lock:
            await self._throttle()
            return AdList(ads=await self._list_ads_unlocked())

    async def _list_ads_unlocked(self) -> list[Ad]:
        page = await self._goto("/account")
        await page.wait_for_selector("table tbody tr", timeout=15_000)
        await page.wait_for_timeout(500)

        rows = page.locator("table tbody tr")
        result: list[Ad] = []

        for i in range(await rows.count()):
            row = rows.nth(i)
            cells = row.locator("td")
            n = await cells.count()
            if n < 15:
                continue
            text0 = (await cells.nth(0).inner_text()).strip()
            if not text0 or text0 == "Loading...":
                continue

            ad_id = await self._extract_ad_id_from_row(row)
            title_cell = cells.nth(0)
            title_link = title_cell.locator("a").first
            title = (
                (await title_link.inner_text()).strip()
                if await title_link.count()
                else text0.split("\n", 1)[0]
            )

            promo_href = None
            for link in await title_cell.locator("a").all():
                href = await link.get_attribute("href") or ""
                if "t.me" in href:
                    promo_href = href
                    break

            budget_link = cells.nth(11).locator("a[href*='edit_budget']").first
            status_link = cells.nth(13).locator("a[href*='edit_status']").first

            result.append(
                Ad(
                    id=ad_id,
                    title=title,
                    promo_url=promo_href,
                    views=parse_int_commas(await cells.nth(1).inner_text()),
                    opened=parse_int_commas(await cells.nth(2).inner_text()),
                    clicks=parse_int_commas(await cells.nth(3).inner_text()),
                    actions=parse_int_commas(await cells.nth(4).inner_text()),
                    ctr=(await cells.nth(5).inner_text()).strip(),
                    cvr=(await cells.nth(6).inner_text()).strip(),
                    cpm=parse_decimal(await cells.nth(7).inner_text()),
                    cpc=parse_decimal(await cells.nth(8).inner_text()),
                    cpa=parse_decimal(await cells.nth(9).inner_text()),
                    spent=parse_decimal(await cells.nth(10).inner_text()),
                    budget=parse_decimal(await cells.nth(11).inner_text()),
                    budget_edit_url=(
                        await budget_link.get_attribute("href")
                        if await budget_link.count()
                        else None
                    ),
                    target=(await cells.nth(12).inner_text()).strip(),
                    status=(await cells.nth(13).inner_text()).strip(),
                    status_edit_url=(
                        await status_link.get_attribute("href")
                        if await status_link.count()
                        else None
                    ),
                    date_added=(await cells.nth(14).inner_text()).strip(),
                )
            )

        return result

    # ------------------------------------------------------------------ get_ad_info

    async def get_ad_info(self, ad_id: int) -> AdInfo:
        async with self._lock:
            await self._throttle()
            page = await self._goto(f"/account/ad/{ad_id}")
            await page.wait_for_selector("input[name=title]", timeout=10_000)

            # Search ads have no ad text field; channels/bots do.
            text_loc = page.locator("textarea[name=text]")
            text = await text_loc.input_value() if await text_loc.count() > 0 else None

            cpm = await page.locator("input[name=cpm]").input_value()
            daily = await page.locator("input[name=daily_budget]").input_value()

            target_type = None
            tt = page.locator("input[name=target_type]")
            if await tt.count() > 0:
                target_type = await tt.input_value()

            status_map = {"1": "Active", "0": "On Hold"}
            status = None
            for radio in await page.locator("input[name=active]").all():
                if await radio.is_checked():
                    status = status_map.get(await radio.input_value())
                    break

            views_limit = None
            for radio in await page.locator("input[name=views_per_user]").all():
                if await radio.is_checked():
                    views_limit = await radio.input_value()
                    break

            picture = page.locator("input[name=picture]")
            show_bot_picture = await picture.is_checked() if await picture.count() > 0 else False

            return {
                "id": ad_id,
                "title": await page.locator("input[name=title]").input_value(),
                "text": text,
                "url": await page.locator("input[name=promote_url]").input_value(),
                "website_name": await self._optional_input(
                    page.locator("input[name=website_name]")
                ),
                "show_bot_picture": show_bot_picture,
                "cpm": parse_decimal(cpm),
                "daily_budget": parse_decimal(daily) if daily else None,
                "daily_views_limit": views_limit,
                "status": cast(AdStatus | None, status),
                "target_type": target_type,
                "targets": await self._read_targets(page),
                "excluded_countries": await self._read_excluded_countries(page),
                "targets_readonly": True,
            }

    async def _optional_input(self, locator: Locator) -> str | None:
        if await locator.count() == 0:
            return None
        value = await locator.first.input_value()
        return value or None

    # ------------------------------------------------------------------ update_ad

    async def update_ad(
        self,
        ad_id: int,
        *,
        title: str | None = None,
        text: str | None = None,
        url: str | None = None,
        website_name: str | None = None,
        show_bot_picture: bool | None = None,
        daily_budget: float | None = None,
        daily_views_limit: int | None = None,
        status: AdStatus | None = None,
        confirm: bool = False,
    ) -> ActionResult:
        params = {
            k: v
            for k, v in {
                "ad_id": ad_id,
                "title": title,
                "text": text,
                "url": url,
                "website_name": website_name,
                "show_bot_picture": show_bot_picture,
                "daily_budget": daily_budget,
                "daily_views_limit": daily_views_limit,
                "status": status,
            }.items()
            if v is not None
        }
        if dry := self._dry_or_run("update_ad", params, confirm=confirm):
            return dry

        async with self._lock:
            await self._throttle()
            page = await self._goto(f"/account/ad/{ad_id}")

            if title is not None:
                await page.get_by_placeholder("E.g., My first ad").fill(title)
            if text is not None:
                await page.get_by_placeholder("Enter your ad text").fill(text)
            if url is not None:
                await page.get_by_placeholder("URL of the channel, post or bot you promote").fill(
                    url
                )
            if website_name is not None:
                await page.get_by_placeholder("Name of the promoted website").fill(website_name)
            if show_bot_picture is not None:
                cb = page.get_by_label("Show bot picture")
                if show_bot_picture:
                    await cb.check()
                else:
                    await cb.uncheck()
            if daily_budget is not None:
                set_daily = page.get_by_text("Set daily limit", exact=False)
                if await set_daily.count() > 0 and await set_daily.first.is_visible():
                    await set_daily.first.click()
                await page.get_by_placeholder("0.00").nth(1).fill(str(daily_budget))
            if daily_views_limit is not None:
                await page.get_by_role("radio", name=str(daily_views_limit)).check()
            if status is not None:
                await page.get_by_role("radio", name=status).check()

            await page.get_by_role("button", name="Save Changes").click()
            await page.wait_for_url(re.compile(rf"/account/ad/{ad_id}"), timeout=10_000)

            errors = await self._read_validation_errors(page)
            return self._result("update_ad", ad_id=ad_id, changes=params, errors=errors)

    # ------------------------------------------------------------------ modals

    async def set_cpm(self, ad_id: int, cpm: float, *, confirm: bool = False) -> ActionResult:
        params = {"ad_id": ad_id, "cpm": cpm}
        if dry := self._dry_or_run("set_cpm", params, confirm=confirm):
            return dry

        async with self._lock:
            await self._throttle()
            page = await self._goto(f"/account/ad/{ad_id}/edit_cpm")
            await page.locator("form input").first.fill(str(cpm))
            await page.get_by_role("button", name="Save").click()
            errors = await self._read_validation_errors(page)
            return self._result("set_cpm", ad_id=ad_id, changes=params, errors=errors)

    async def set_status(
        self,
        ad_id: int,
        status: AdStatus,
        *,
        confirm: bool = False,
    ) -> ActionResult:
        params: dict[str, Any] = {"ad_id": ad_id, "status": status}
        if dry := self._dry_or_run("set_status", params, confirm=confirm):
            return dry

        async with self._lock:
            await self._throttle()
            page = await self._goto(f"/account/ad/{ad_id}/edit_status")
            await page.get_by_role("radio", name=status).check()
            await page.get_by_role("button", name="Save").click()
            errors = await self._read_validation_errors(page)
            return self._result("set_status", ad_id=ad_id, changes=params, errors=errors)

    async def increase_budget(
        self,
        ad_id: int,
        amount: float,
        *,
        confirm: bool = False,
    ) -> ActionResult:
        params = {"ad_id": ad_id, "delta_ton": amount}
        if dry := self._dry_or_run("increase_budget", params, confirm=confirm):
            return dry

        async with self._lock:
            await self._throttle()
            page = await self._goto(f"/account/ad/{ad_id}/edit_budget")
            await page.locator("form input").first.fill(str(amount))
            await page.get_by_role("button", name="Add to budget").click()
            errors = await self._read_validation_errors(page)
            return self._result("increase_budget", ad_id=ad_id, changes=params, errors=errors)

    async def set_budget(
        self,
        ad_id: int,
        target_budget: float,
        *,
        confirm: bool = False,
    ) -> ActionResult:
        # The preview must not touch the network, so the delta can only be
        # computed against the live budget once confirm=True. The read-only and
        # spend-ceiling gates are applied here so they fire even in preview.
        self.settings.check_can_write("set_budget")
        if not confirm:
            return ActionResult(
                action="set_budget",
                dry_run=True,
                ad_id=ad_id,
                changes={"target_budget": target_budget},
            )
        self.settings.check_spend(target_budget, "set_budget")

        ads = await self.list_ads()
        current = next((a for a in ads["ads"] if a.get("id") == ad_id), None)
        if current is None:
            raise TelegramAdsError(f"Ad {ad_id} not found")
        delta = round(target_budget - current["budget"], 4)
        if delta <= 0:
            raise BudgetError(
                f"Target budget {target_budget} must exceed current {current['budget']}"
            )
        return await self.increase_budget(ad_id, delta, confirm=True)

    # ------------------------------------------------------------------ stats

    async def get_ad_stats_csv(
        self,
        ad_id: int,
        period: StatsPeriod = "days",
        *,
        confirm: bool = False,
    ) -> StatsCsv | ActionResult:
        params = {"ad_id": ad_id, "period": period}
        if dry := self._dry_or_run("get_ad_stats_csv", params, confirm=confirm, mutates=False):
            return dry

        # Site uses period=day (singular); accept "days" as alias.
        site_period = "day" if period in ("day", "days") else "5min"

        async with self._lock:
            await self._throttle()
            page = await self._goto(f"/account/ad/{ad_id}/stats?period={site_period}")
            # Querystring alone may not switch the chart; click the period tab.
            tab_name = "Days" if site_period == "day" else "5 min"
            tab = page.get_by_role("link", name=tab_name)
            if await tab.count() > 0:
                await tab.first.click()
                await page.wait_for_timeout(400)

            # Chart CSV; avoid budget-chart CSV and monthly report CSV.
            csv_link = page.locator(
                f"a.csv_link[href*='/csv?'][href*='period={site_period}']:not([href*='budget'])"
            ).first
            if await csv_link.count() == 0:
                csv_link = page.locator("#chart_count_stats_wrap a.csv_link").first
            async with page.expect_download() as dl_info:
                await csv_link.click()
            download = await dl_info.value
            path = await download.path()
            if path is None:
                raise TelegramAdsError("Download path is unavailable")
            # Read off the event loop: a large export on a slow disk would
            # otherwise stall every other task in the process.
            raw = await asyncio.to_thread(Path(path).read_bytes)

        # The CSV is remote content heading for a model's context. Cap it so a
        # large export cannot flood the window; say so rather than truncating
        # silently.
        text = raw.decode("utf-8", errors="replace")
        if len(text) > MAX_CSV_CHARS:
            text = (
                text[:MAX_CSV_CHARS]
                + f"\n... [truncated at {MAX_CSV_CHARS} of {len(text)} characters]"
            )
        return StatsCsv(ad_id=ad_id, period=period, csv=text)

    # ------------------------------------------------------------------ create_ad

    async def create_ad(
        self,
        *,
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
    ) -> ActionResult:
        params: dict[str, Any] = {
            "title": title,
            "text": text,
            "url": url,
            "cpm": cpm,
            "initial_budget": initial_budget,
            "target_type": target_type,
            "targets": targets or [],
            "website_name": website_name,
            "show_bot_picture": show_bot_picture,
            "daily_views_limit": daily_views_limit,
            "status": status,
            "clear_draft": clear_draft,
        }
        if dry := self._dry_or_run("create_ad", params, confirm=confirm):
            return dry

        async with self._lock:
            await self._throttle()
            page = await self._goto("/account/ad/new")

            if clear_draft:
                clear = page.get_by_role("link", name="Clear Draft")
                if await clear.count() == 0:
                    clear = page.get_by_text("Clear Draft", exact=True)
                if await clear.count() > 0 and await clear.first.is_visible():
                    await clear.first.click()

            await page.get_by_role("radio", name=target_type).check()
            await page.get_by_placeholder("E.g., My first ad").fill(title)
            await page.get_by_placeholder("Enter your ad text").fill(text)
            await page.get_by_placeholder("URL of the channel, post or bot you promote").fill(url)

            if website_name:
                await page.get_by_placeholder("Name of the promoted website").fill(website_name)
            if show_bot_picture:
                await page.get_by_label("Show bot picture").check()

            await page.get_by_placeholder("0.00").first.fill(str(cpm))
            await page.get_by_label("Initial budget in Ton").fill(str(initial_budget))
            await page.get_by_role("radio", name=str(daily_views_limit)).check()
            await (
                page.locator("label", has_text="Initial status")
                .locator("..")
                .get_by_role("radio", name=status)
                .check()
            )

            if targets:
                await self._add_targets(page, target_type, targets)

            await page.get_by_label("I have read and agree with Terms of Service").check()
            await page.get_by_role("button", name="Create Ad").click()

            await page.wait_for_url(re.compile(r"/account/ad/\d+"), timeout=15_000)
            match = _AD_ID_RE.search(page.url)
            new_id = int(match.group(1)) if match else None

            errors = await self._read_validation_errors(page)
            return self._result("create_ad", ad_id=new_id, changes=params, errors=errors)

    async def _add_targets(self, page: Page, target_type: TargetType, targets: list[str]) -> None:
        placeholders = {
            "channels": "t.me channel URL",
            "bots": "t.me bot URL",
            "search": "search query",
        }
        placeholder = placeholders[target_type]
        field = page.get_by_placeholder(placeholder)
        if await field.count() == 0:
            field = page.locator(f"input[placeholder*='{placeholder.split()[0]}']")
        for target in targets:
            await field.first.fill(target)
            await field.first.press("Enter")

    # ------------------------------------------------------------------ read-only

    async def get_account_budget(self) -> AccountBudget:
        """Account-level budget page: current balance + transaction ledger."""
        async with self._lock:
            await self._throttle()
            page = await self._goto("/account/budget")
            await page.wait_for_timeout(300)

            current = None
            budget_link = page.locator("a[href='/account/budget']").first
            if await budget_link.count() > 0:
                current = parse_decimal(await budget_link.inner_text())

            fragment = page.get_by_role("link", name="Add Funds on Fragment")
            fragment_url = await fragment.get_attribute("href") if await fragment.count() else None

            transactions: list[Transaction] = []
            rows = page.locator("table tbody tr")
            for i in range(await rows.count()):
                cells = rows.nth(i).locator("td")
                if await cells.count() < 3:
                    continue
                desc = (await cells.nth(0).inner_text()).strip()
                amount_raw = (await cells.nth(1).inner_text()).strip()
                date = (await cells.nth(2).inner_text()).strip()
                sign = -1 if amount_raw.lstrip().startswith("-") else 1
                amount = sign * parse_decimal(amount_raw)
                ad_link = cells.nth(0).locator("a[href*='/account/ad/']").first
                ad_id = None
                ad_title = None
                if await ad_link.count() > 0:
                    ad_id = extract_ad_id(await ad_link.get_attribute("href"))
                    ad_title = (await ad_link.inner_text()).strip()
                transactions.append(
                    Transaction(
                        description=desc,
                        amount=amount,
                        date=date,
                        ad_id=ad_id,
                        ad_title=ad_title,
                    )
                )

            return AccountBudget(
                current_budget=current,
                fragment_url=fragment_url,
                transactions=transactions,
            )
