# Contributing

Thanks for your interest in improving `telegram-ads-mcp`. This project is an
MCP stdio server (Python SDK 2.x) that drives
[ads.telegram.org](https://ads.telegram.org) via Playwright, so contributions
typically touch the MCP tool surface, the Playwright client, or the
packaging/docs/tests around them.

## Dev setup

```bash
git clone https://github.com/Free-cat/telegram_ads_mcp.git
cd telegram_ads_mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

`pip install -e ".[dev]"` installs the package in editable mode plus
`pytest`, `ruff`, and `pyright`.

## Layout

| Path | Role |
|------|------|
| `mcp_server.py` | Tool definitions and the MCP boundary. Translates domain errors into `ToolError`. |
| `client.py` | All Playwright automation. Knows nothing about MCP. |
| `models.py` | TypedDicts. A tool's return annotation becomes its published `outputSchema`. |
| `settings.py` | Environment safety gates (read-only, spend ceiling). |
| `exceptions.py` | Coded domain errors. |
| `paths.py` | Session file location and permissions. |
| `auth_setup.py` | Interactive one-time login. |

Keep `client.py` free of MCP imports — it is meant to be usable as a library,
and it is what the tests exercise without a browser.

## Running checks

Run these before opening a PR:

```bash
ruff check src tests
ruff format --check src tests
pyright
pytest
```

CI runs all four on Python 3.11–3.14, plus a wheel build that performs a real
stdio handshake and an sdist check that fails if a session file is ever
included.

- `pytest` runs the default test suite (parsing helpers, dry-run payloads,
  operator gates, error channels, auth path resolution, tool annotations and
  output schemas). These tests do not touch the real Telegram Ads site or start
  a browser.
- Tests marked `live` hit the real `ads.telegram.org` and are **not** run by
  default or in CI. They require a real session (`TELEGRAM_ADS_AUTH_STATE`,
  `TELEGRAM_ADS_ACCOUNT`) and `RUN_LIVE_TESTS=1`. Only run these against a
  disposable/test ad account if you choose to run them locally.

## Never commit auth state

`auth_state.json` contains live session credentials for your Telegram Ads
account. It is already excluded via `.gitignore` (`auth_state.json` and
`**/auth_state.json`), and CI scans tracked files for anything shaped like a
Playwright storage state — but always double-check `git status` / `git diff`
before committing or pushing, especially if you changed the default auth
path logic in `paths.py`. Never paste its contents into an issue, PR
description, or commit message.

## Making changes

- Keep the mutating-tool safety pattern intact: every write/spend tool must
  default to `confirm=False` and return a preview that accurately reflects what
  `confirm=True` would do, and must go through `_dry_or_run` so the operator
  gates in `settings.py` always apply. Don't add a state-changing tool without
  this gate.
- New tools return a TypedDict from `models.py`. The return annotation *is* the
  published `outputSchema`, so a bare `dict` silently drops structured output
  for that tool. Add a contract test for the schema.
- Domain failures raise a `TelegramAdsError` subclass with a stable `code`, and
  the tool translates it with `_as_tool_error`. Anything else is treated as a
  crash and the message is withheld from the model — so an anticipated failure
  raised as a plain exception is a bug.
- Set MCP tool annotations explicitly (`read_only_hint`, `destructive_hint`,
  `idempotent_hint`, `open_world_hint`). Remember `destructive_hint` defaults
  to true when unset, and that these are UX hints, not a security boundary —
  the `confirm` gate and `settings.py` are.
- Update `README.md`'s tools table if you add, remove, or change the
  signature/behavior of a tool.
- Prefer small, focused PRs.

## PR checklist

Before requesting review, confirm:

- [ ] `ruff check src tests` and `ruff format --check src tests` pass
- [ ] `pyright` passes with no new errors
- [ ] `pytest` passes locally
- [ ] No `auth_state.json` or other session/credential data is included in the diff
- [ ] New or changed tools keep the `confirm=False` preview default and go
      through `_dry_or_run` (if state-changing)
- [ ] New tools declare a TypedDict return type and a title
- [ ] `README.md` tools table and docs are updated if the tool surface changed
- [ ] Commit messages and PR description explain the "why", not just the "what"
