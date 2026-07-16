# Contributing

Thanks for your interest in improving `telegram-ads-mcp`. This project is a
FastMCP stdio server that drives [ads.telegram.org](https://ads.telegram.org)
via Playwright, so contributions typically touch the MCP tool surface, the
Playwright client, or the packaging/docs/tests around them.

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

## Running checks

Run these before opening a PR:

```bash
pytest
ruff check .
pyright
```

- `pytest` runs the default test suite (parsing helpers, dry-run payloads,
  auth path resolution, tool annotations). These tests do not touch the real
  Telegram Ads site.
- Tests marked `live` hit the real `ads.telegram.org` and are **not** run by
  default or in CI. They require a real session (`TELEGRAM_ADS_AUTH_STATE`,
  `TELEGRAM_ADS_ACCOUNT`) and `RUN_LIVE_TESTS=1`. Only run these against a
  disposable/test ad account if you choose to run them locally.
- `ruff check .` lints the codebase.
- `pyright` type-checks `src/`.

## Never commit auth state

`auth_state.json` contains live session credentials for your Telegram Ads
account. It is already excluded via `.gitignore` (`auth_state.json` and
`**/auth_state.json`), but always double-check `git status` / `git diff`
before committing or pushing, especially if you changed the default auth
path logic in `paths.py`. Never paste its contents into an issue, PR
description, or commit message.

## Making changes

- Keep the mutating-tool safety pattern intact: every write/spend tool must
  default to `confirm=False` and return a dry-run preview that accurately
  reflects what `confirm=True` would do. Don't add a tool that mutates state
  without this gate.
- Update MCP tool annotations (`readOnlyHint`, `destructiveHint`,
  `openWorldHint`) if you add or change a tool, and remember these are UX
  hints, not a security boundary — the `confirm` gate is.
- Update `README.md`'s tools table if you add, remove, or change the
  signature/behavior of a tool.
- Prefer small, focused PRs.

## PR checklist

Before requesting review, confirm:

- [ ] `pytest` passes locally
- [ ] `ruff check .` passes with no new warnings
- [ ] `pyright` passes with no new errors
- [ ] No `auth_state.json` or other session/credential data is included in the diff
- [ ] New or changed tools keep the `confirm=False` dry-run default (if mutating)
- [ ] `README.md` tools table and docs are updated if the tool surface changed
- [ ] Commit messages and PR description explain the "why", not just the "what"
