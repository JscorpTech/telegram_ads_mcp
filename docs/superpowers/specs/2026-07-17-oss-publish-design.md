# Telegram Ads MCP — Open Source Publish Design

**Date:** 2026-07-17  
**Status:** Approved for planning  
**License:** MIT  
**First public goal:** GitHub repository (installable, documented solid v0.1)

## Context

`telegram-ads-mcp` is a working FastMCP stdio server that drives [ads.telegram.org](https://ads.telegram.org) through Playwright and a reused browser session (`auth_state.json`). The repo currently has working code but no commits, no public docs, no LICENSE, and a flat module layout that is awkward for `uvx`/`pipx` install.

This design covers preparing the project for a first open-source GitHub release. PyPI and official MCP Registry publication are explicitly deferred.

## Goals

1. Publish a GitHub repo that strangers can clone or install and run in Cursor/Claude Desktop.
2. Keep the **full current tool surface** (read + mutate + create + budget).
3. Keep financial and download actions gated with `confirm=False` dry-run by default.
4. Document security clearly: session file is a secret; agents can spend money if confirm is passed.
5. Ship a solid v0.1 packaging/docs/tests/CI baseline without Docker, remote HTTP, or registry publish.

## Non-goals (v0.1)

- PyPI or MCP Registry listing
- Docker image / remote Streamable HTTP transport
- Audit logging, rate limits, OS keychain integration
- Live Telegram Ads E2E in CI (requires private session)
- Automating Fragment top-up, Ad Schedule, or Similar channels/bots widgets

## Decisions already locked

| Topic | Choice |
|-------|--------|
| First publish target | GitHub only |
| Tool surface | Full API (all current tools) |
| License | MIT |
| Install UX | Dual: one-liner (`uvx`/`pipx` or git) + clone/editable fallback |
| Docs language | English only |
| Readiness bar | Solid v0.1 (not minimal, not enterprise-hardened) |
| Approach | Docs-first polish with src-layout packaging |

## Architecture

### Package layout

```text
telegram-ads-mcp/
  LICENSE
  README.md
  CONTRIBUTING.md
  SECURITY.md
  pyproject.toml
  .gitignore
  .github/workflows/ci.yml
  src/
    telegram_ads_mcp/
      __init__.py
      __main__.py          # python -m telegram_ads_mcp
      mcp_server.py
      client.py            # Playwright client (today: telegram_ads_client.py)
      auth_setup.py
      parsing.py
      exceptions.py
  tests/
    test_parsing.py
    test_dry_run.py
    test_auth_paths.py
    test_tool_annotations.py
```

### Packaging rules

- Use **src-layout** and hatchling.
- Console script: `telegram-ads-mcp` → `telegram_ads_mcp.mcp_server:main`.
- Also support `python -m telegram_ads_mcp`.
- `requires-python = ">=3.11"`, version `0.1.0`.
- Dependencies remain `mcp` and `playwright`.
- README must document `playwright install chromium` after install.

### Auth state path

Default resolution order:

1. Env `TELEGRAM_ADS_AUTH_STATE` if set
2. `~/.config/telegram-ads-mcp/auth_state.json`
3. Fallback: `./auth_state.json` in cwd (dev compatibility)

`auth_setup` writes to the resolved path and prints it. File must never be committed. Prefer `0600` permissions when creating/updating the file.

Account selection remains via `TELEGRAM_ADS_ACCOUNT` (substring match on Choose Account).

## Tool surface and safety

### Read-only tools

Annotations: `readOnlyHint=true`, `openWorldHint=true`

- `list_accounts`
- `list_ads`
- `get_ad_info`
- `get_account_budget`

### Mutating / side-effect tools

Default: `confirm=False` returns a structured dry-run preview and does **not** raise.

| Tool | destructiveHint | Gate |
|------|-----------------|------|
| `set_cpm` | false | `confirm=False` dry-run |
| `set_status` | false | `confirm=False` dry-run |
| `update_ad` | false | `confirm=False` dry-run |
| `create_ad` | false | `confirm=False` dry-run |
| `increase_budget` | true | `confirm=False` dry-run |
| `set_budget` | true | `confirm=False` dry-run |
| `get_ad_stats_csv` | false | `confirm=False` dry-run (download side-effect) |

Additional rules:

1. Docstrings must state that execution requires `confirm=True`.
2. Stable `AUTH_EXPIRED` error for expired/invalid sessions.
3. Transport for v0.1 is **stdio only**.
4. MCP tool annotations must be set accurately for client UX (not as a security boundary).

## Documentation

### README.md (English)

Required sections:

1. What it is
2. Security warning (`auth_state.json`, spend risk)
3. Requirements
4. Quick start (auth setup + Cursor config + Playwright browsers)
5. Clone / editable install fallback
6. Tools table (name, read/write, confirm required)
7. Config env vars
8. Limitations
9. License (MIT)

### SECURITY.md

- Treat session file as a secret
- Restrict file permissions
- Do not give untrusted agents write tools without human review
- Revoke by deleting auth state and logging out of Telegram Ads

### CONTRIBUTING.md

- Dev setup
- Lint/test commands
- Never commit auth state
- PR checklist

### Install examples

Provide both:

1. One-liner style install from git (exact `uvx`/`pipx` command finalized in implementation plan)
2. Clone + venv + `pip install -e .` for contributors

Cursor `mcp.json` example must pass `TELEGRAM_ADS_AUTH_STATE` and optionally `TELEGRAM_ADS_ACCOUNT`.

## Testing and CI

### Default automated tests (no live session)

- Parsing helpers (ints with commas, decimals, ad IDs)
- Auth path resolution
- Dry-run payloads for every mutating tool
- Input validation for status/period/positive amounts
- Tool registration + annotations
- Mocked Playwright flows for account selection and auth-expired detection where practical

### Live tests

- Marked `live`, off by default
- Require `TELEGRAM_ADS_AUTH_STATE`, `TELEGRAM_ADS_ACCOUNT`, and `RUN_LIVE_TESTS=1`
- Not run in CI

### GitHub Actions

On push/PR:

1. Python 3.11–3.14 matrix
2. Install package
3. Ruff lint
4. Pyright typecheck
5. Pytest
6. Build wheel and verify entrypoint import/install

Keep unit tests fast; Chromium install only if a mocked browser smoke job needs it.

## Implementation outline (for planning)

1. Restructure to `src/telegram_ads_mcp/` and fix imports/entrypoints
2. Auth path defaults + `.gitignore` hardening
3. Add MCP annotations and confirm dry-run consistency audit
4. Write LICENSE, README, CONTRIBUTING, SECURITY
5. Add tests and GitHub Actions CI
6. First meaningful git history / tag `v0.1.0` after green CI

## Open points for implementation plan

- Exact preferred one-liner (`uvx` vs `pipx` vs `pip install git+...`) after verifying Playwright browser install UX
- Whether `server.json` stub is included as a non-published placeholder or omitted entirely until registry work
- Whether Pyright is strict or basic for v0.1

These do not block the design; they are decided during planning/implementation.
