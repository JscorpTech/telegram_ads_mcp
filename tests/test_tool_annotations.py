"""Contract tests: every mutating tool must carry accurate ToolAnnotations.

Annotations are hints for client consent UX, not a security boundary, but a
wrong hint is still a defect: `destructiveHint` defaults to true when unset, so
an additive tool that stays silent is advertised as destructive, and a
spend-capable tool that claims to be additive understates its risk.

Field access is snake_case in SDK 2.x (construction still accepts camelCase).
"""

import asyncio

import pytest

from telegram_ads_mcp import mcp_server

# (name, read_only, destructive, idempotent)
EXPECTED = {
    "list_accounts": (True, None, True),
    "list_ads": (True, None, True),
    "get_ad_info": (True, None, True),
    "get_account_budget": (True, None, True),
    # Drives a browser download but changes nothing on the account.
    "get_ad_stats_csv": (True, None, True),
    "update_ad": (False, False, True),
    "set_cpm": (False, False, True),
    "set_status": (False, False, True),
    # Money: adding budget is not idempotent, and creating an ad replaces the
    # draft, so neither may be advertised as purely additive.
    "increase_budget": (False, True, False),
    "set_budget": (False, True, False),
    "create_ad": (False, True, False),
}


def _tools_by_name():
    return {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_every_tool_has_annotations():
    for name, tool in _tools_by_name().items():
        assert tool.annotations is not None, f"{name} has no annotations"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_annotation_profile(name: str):
    read_only, destructive, idempotent = EXPECTED[name]
    ann = _tools_by_name()[name].annotations
    assert ann is not None
    assert ann.read_only_hint is read_only
    assert ann.destructive_hint is destructive
    assert ann.idempotent_hint is idempotent
    assert ann.open_world_hint is True


def test_spend_tools_are_destructive():
    """Regression: create_ad was previously grouped with the additive writes."""
    tools = _tools_by_name()
    for name in ("increase_budget", "set_budget", "create_ad"):
        ann = tools[name].annotations
        assert ann is not None
        assert ann.destructive_hint is True


def test_every_tool_has_a_title():
    """Titles are a published requirement for client-side consent prompts."""
    for name, tool in _tools_by_name().items():
        assert tool.title, f"{name} has no title"
        assert tool.title != name, f"{name} title should be human-readable"


def test_every_tool_publishes_an_output_schema():
    """A bare `dict` return would publish no schema and no structuredContent."""
    for name, tool in _tools_by_name().items():
        assert tool.output_schema is not None, f"{name} has no output schema"
        assert isinstance(tool.output_schema, dict)


def test_no_argument_tools_declare_empty_input():
    for name in ("list_accounts", "list_ads", "get_account_budget"):
        schema = _tools_by_name()[name].input_schema
        assert schema.get("type") == "object"
        assert schema.get("properties", {}) == {}
