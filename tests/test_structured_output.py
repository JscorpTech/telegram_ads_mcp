"""Contract tests: the wire shape of structured output.

A tool's return annotation becomes its published `outputSchema` and its
`structuredContent`. Two failure modes this pins down:

* A bare `dict` return publishes no schema and no structured content, silently
  dropping the payload for clients that parse results.
* A `Union` (or `CallToolResult`) return annotation makes the SDK wrap the value
  in a `{"result": ...}` envelope and validate against it, so a plain flat dict
  raises at call time — on the default preview path, for every mutating tool.
"""

import asyncio

from telegram_ads_mcp import mcp_server
from telegram_ads_mcp.models import ActionResult


class _FakeClient:
    async def increase_budget(self, ad_id: int, amount: float, confirm: bool = False):
        return ActionResult(
            action="increase_budget",
            dry_run=not confirm,
            changes={"ad_id": ad_id, "delta_ton": amount},
        )

    async def update_ad(self, ad_id: int, **kwargs):
        return ActionResult(
            action="update_ad",
            dry_run=True,
            ad_id=ad_id,
            changes={"title": kwargs.get("title")},
            errors=["Title too long"],
        )


class _Holder:
    async def get(self):
        return _FakeClient()


def _run(name: str, args: dict):
    original = mcp_server._client
    mcp_server._client = lambda ctx: _Holder()
    try:
        tool = mcp_server.mcp._tool_manager.get_tool(name)
        return asyncio.run(tool.run(args, None, convert_result=True))
    finally:
        mcp_server._client = original


def test_preview_payload_reaches_structured_content_flat():
    """No `{"result": ...}` envelope: the payload is the object itself."""
    result = _run("increase_budget", {"ad_id": 3, "amount": 2.0})
    assert result.is_error is False
    assert result.structured_content == {
        "action": "increase_budget",
        "dry_run": True,
        "changes": {"ad_id": 3, "delta_ton": 2.0},
    }


def test_validation_errors_ride_along_in_structured_content():
    result = _run("update_ad", {"ad_id": 5, "title": "hi"})
    assert result.structured_content is not None
    assert result.structured_content["errors"] == ["Title too long"]
    assert result.structured_content["changes"]["title"] == "hi"


def test_text_block_is_still_present_for_compatibility():
    """The spec asks structured tools to keep a serialized text rendering."""
    result = _run("update_ad", {"ad_id": 5, "title": "hi"})
    assert result.content
    assert "Title too long" in result.content[0].text


# ------------------------------------------------------------ input validation


def _validate(name: str, args: dict) -> str:
    """Return the rejection text the model would see for bad arguments."""
    import pytest
    from mcp.server.mcpserver.exceptions import ToolError

    tool = mcp_server.mcp._tool_manager.get_tool(name)
    with pytest.raises(ToolError) as excinfo:
        asyncio.run(tool.run(args, None, convert_result=True))
    return str(excinfo.value)


def test_money_arguments_reject_non_positive_values():
    """A negative budget would be nonsense; the schema says so before any I/O."""
    assert "greater than 0" in _validate("increase_budget", {"ad_id": 3, "amount": -5})
    assert "greater than 0" in _validate("set_cpm", {"ad_id": 3, "cpm": 0})
    assert "greater than 0" in _validate("set_cpm", {"ad_id": 0, "cpm": 0.2})


def test_create_ad_rejects_a_zero_initial_budget():
    text = _validate(
        "create_ad",
        {
            "title": "t",
            "text": "x",
            "url": "t.me/b",
            "cpm": 0.2,
            "initial_budget": 0,
        },
    )
    assert "initial_budget" in text


def test_status_is_constrained_to_the_real_values():
    """The rejection names the valid options, so the model can retry correctly."""
    text = _validate("set_status", {"ad_id": 3, "status": "Bogus"})
    assert "'Active' or 'On Hold'" in text
