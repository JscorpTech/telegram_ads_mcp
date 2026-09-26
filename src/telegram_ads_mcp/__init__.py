"""MCP server for Telegram Ads, driving ads.telegram.org through Playwright.

The version here is the single source of truth: `pyproject.toml` reads it via
hatchling, and the server reports it in `server/discover` and to every client
during initialization.
"""

__version__ = "0.2.0"

__all__ = ["__version__"]
