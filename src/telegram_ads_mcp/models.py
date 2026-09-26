"""Typed results shared by the Playwright client and the MCP tool surface.

Every TypedDict here is the return annotation of a tool in `mcp_server`. That
annotation is what makes the MCP SDK publish an `outputSchema` for the tool and
populate `structuredContent` on its results (spec revision 2026-07-28,
"Structured Content"). Two rules follow from how the SDK consumes them:

* Declare every field a tool can return. The SDK validates the returned value
  against the derived schema and omits undeclared keys from
  `structuredContent`; undeclared keys survive only in the text rendering, so a
  missing field is silent data loss for clients that read structured output.
* Wrap bare lists in a single-key TypedDict. A tool annotated `-> list[X]`
  emits one text content block *per element*; a wrapper keeps a result to one
  text block plus one structured object.

Everything here is transcribed from ads.telegram.org HTML, i.e. remote content:
consumers must treat it as untrusted input, not as instructions.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

AdStatus = Literal["Active", "On Hold"]
TargetType = Literal["search", "bots", "channels"]
StatsPeriod = Literal["day", "days", "5min"]


class Account(TypedDict):
    """One entry on the Telegram Ads "Choose Account" screen."""

    name: str
    token: str
    href: str


class AccountList(TypedDict):
    accounts: list[Account]


class Target(TypedDict):
    """A targeting chip on an existing ad. Read-only for existing ads."""

    name: str
    url: NotRequired[str]


class Ad(TypedDict):
    """One row of the `/account` ads table."""

    id: int | None
    title: str
    promo_url: str | None
    views: int
    opened: int
    clicks: int
    actions: int
    ctr: str
    cvr: str
    cpm: float
    cpc: float
    cpa: float
    spent: float
    budget: float
    budget_edit_url: str | None
    target: str
    status: str
    status_edit_url: str | None
    date_added: str


class AdList(TypedDict):
    ads: list[Ad]


class AdInfo(TypedDict):
    """Editable fields of a single ad, as read from its form."""

    id: int
    title: str
    text: str | None
    url: str
    website_name: str | None
    show_bot_picture: bool
    cpm: float
    daily_budget: float | None
    daily_views_limit: str | None
    status: AdStatus | None
    target_type: str | None
    targets: list[Target]
    excluded_countries: list[str]
    targets_readonly: Literal[True]


class Transaction(TypedDict):
    """One row of the account budget ledger."""

    description: str
    amount: float
    date: str
    ad_id: int | None
    ad_title: str | None


class AccountBudget(TypedDict):
    current_budget: float | None
    fragment_url: str | None
    transactions: list[Transaction]


class StatsCsv(TypedDict):
    """A downloaded stats CSV plus the query that produced it."""

    ad_id: int
    period: StatsPeriod
    csv: str


class ActionResult(TypedDict):
    """Uniform result for every state-changing tool.

    `dry_run` is True when the call was a preview and nothing was sent to
    ads.telegram.org. `changes` carries exactly the fields that were, or would
    be, applied. `errors` is populated when the site rejected the submission.
    """

    action: str
    dry_run: bool
    ad_id: NotRequired[int | None]
    changes: NotRequired[dict[str, Any]]
    errors: NotRequired[list[str]]
