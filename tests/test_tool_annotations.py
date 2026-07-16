"""Contract tests: every mutating FastMCP tool must carry accurate ToolAnnotations."""

from telegram_ads_mcp.mcp_server import mcp


def _tools_by_name():
    return {t.name: t for t in mcp._tool_manager.list_tools()}


def test_read_tools_marked_readonly():
    tools = _tools_by_name()
    for name in ("list_accounts", "list_ads", "get_ad_info", "get_account_budget"):
        ann = tools[name].annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is True


def test_budget_tools_marked_destructive():
    tools = _tools_by_name()
    for name in ("increase_budget", "set_budget"):
        ann = tools[name].annotations
        assert ann is not None
        assert ann.readOnlyHint is False
        assert ann.destructiveHint is True
        assert ann.openWorldHint is True


def test_non_budget_writes_not_destructive():
    tools = _tools_by_name()
    for name in ("set_cpm", "set_status", "update_ad", "create_ad", "get_ad_stats_csv"):
        ann = tools[name].annotations
        assert ann is not None
        assert ann.readOnlyHint is False
        assert ann.destructiveHint is False
