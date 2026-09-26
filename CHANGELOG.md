# Changelog

Notable changes per release. This project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0]

### Fixed

- **The published package no longer fails to start.** `0.1.0` declared
  `mcp>=1.0.0`, which resolves to MCP Python SDK 2.x — where `FastMCP` was
  renamed to `MCPServer` and `mcp.server.fastmcp` was deleted. A fresh install
  raised `ModuleNotFoundError` on import. The dependency is now bounded
  (`mcp>=2.2,<3`) and the server is ported to the 2.x API.
- **`AUTH_EXPIRED` now reaches the model.** Every tool used to re-raise an
  expired session as `RuntimeError`, which SDK 2.x treats as a crash and
  reduces to a generic `Error executing tool <name>` — the actionable part was
  dropped. Domain errors are now raised as `ToolError` with their code intact.
- **The Chromium process is now closed on shutdown.** The old `atexit` hook
  called `asyncio.get_event_loop()` after `anyio.run` had finished, which
  raises `RuntimeError` on a modern Python; the bare `except: pass` hid it, so
  the browser leaked on every exit. Shutdown is now a lifespan scope.
- **`create_ad` is annotated destructive.** It is grouped with the tools that
  spend TON, but was advertised as additive-only, and a test locked that
  mismatch in.
- **A missing session file is an error, not a startup crash**, so the server
  can tell the agent to run `telegram-ads-auth`.

### Added

- **Structured output.** Every tool publishes an `outputSchema` and returns
  `structuredContent`, so clients can parse results instead of reading prose.
- **Operator-level safety gates** (see SECURITY.md): `TELEGRAM_ADS_READ_ONLY=1`
  refuses every state-changing tool regardless of `confirm`, and
  `TELEGRAM_ADS_MAX_SPEND_TON` caps any single budget increase.
- **Tool metadata**: a human-readable `title` per tool, server `instructions`,
  and `idempotent_hint` on the tools where repeating a call is safe.
- **Input validation** on money and id parameters (`ad_id > 0`, `cpm > 0`,
  `amount > 0`), enforced by the SDK from the schema.
- **Rate limiting**: browser calls are spaced, so a looping agent cannot hammer
  ads.telegram.org.
- **Bounded untrusted output**: a downloaded stats CSV is truncated with an
  explicit marker rather than passed through in full.
- **`server.json`** for the official MCP Registry, plus the `mcp-name` marker in
  the README that proves PyPI ownership.
- CI: `ruff format --check`, a wheel smoke test that performs a real stdio
  handshake, an sdist contents check that fails if a session file is included,
  and a gitleaks job.
- Dependabot, issue and pull-request templates.

### Changed

- Package split for testability: `models.py` (result types) and `settings.py`
  (environment gates) are new; `exceptions.py` gained a coded error hierarchy.
- `get_ad_info` now returns `cpm` and `daily_budget` as numbers rather than
  strings, and `get_ad_stats_csv` returns the CSV in a structured envelope with
  the ad id and period.
- README documents Claude Code, Claude Desktop, Cursor and VS Code setup, the
  `uv tool install` path, and the safety controls.
- SECURITY.md gains supported versions, an explicit scope statement, and the
  trust-boundary exclusions.
- `auth_setup` refuses to save a half-authenticated session instead of warning
  and saving anyway.

[0.2.0]: https://github.com/Free-cat/telegram_ads_mcp/releases/tag/v0.2.0
