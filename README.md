# telegram-ads-mcp

An [MCP](https://modelcontextprotocol.io) server that lets AI agents (Cursor,
Claude Desktop, etc.) read and manage your [Telegram Ads](https://ads.telegram.org)
campaigns — list accounts and ads, read stats and budgets, and create/update
ads, CPM, status, and budget — by driving the real ads.telegram.org web UI
through Playwright with a reused, cookie-based login session.

> **⚠️ Security warning**
>
> This server reuses a saved Telegram Ads browser session
> (`auth_state.json`). That file is equivalent to your login credentials for
> ads.telegram.org — anyone with it can act as you, **including spending your
> TON ad budget**. Never commit it, share it, or check it into version
> control. Mutating and financial tools (`update_ad`, `set_cpm`, `set_status`,
> `increase_budget`, `set_budget`, `create_ad`, `get_ad_stats_csv`) default to
> a safe `confirm=False` dry-run and only take effect when an agent explicitly
> passes `confirm=True`. Read [SECURITY.md](SECURITY.md) before connecting
> this server to any agent you don't fully trust with your ad spend.

## Requirements

- Python 3.11+
- Chromium, installed via Playwright (`playwright install chromium`)
- A Telegram Ads account with access to [ads.telegram.org](https://ads.telegram.org)

## Quick start (recommended: clone)

Cloning and installing in a virtualenv is the recommended path — it makes the
one-time interactive login step and the Playwright browser install
straightforward and reproducible.

```bash
git clone https://github.com/Free-cat/telegram_ads_mcp.git
cd telegram_ads_mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
telegram-ads-auth
```

`telegram-ads-auth` opens a real (visible) browser window so you can log in
to Telegram, choose the ads account you want to manage, and save the session.
It prints the path it saved to (by default
`~/.config/telegram-ads-mcp/auth_state.json`).

### Cursor configuration

Add the server to your `mcp.json`, using the **absolute path** to the console
script inside the venv you just created:

```json
{
  "mcpServers": {
    "telegram-ads": {
      "command": "/ABS/PATH/telegram_ads_mcp/.venv/bin/telegram-ads-mcp",
      "env": {
        "TELEGRAM_ADS_ACCOUNT": "Artem",
        "TELEGRAM_ADS_AUTH_STATE": "/ABS/PATH/to/auth_state.json"
      }
    }
  }
}
```

Restart Cursor (or reload MCP servers) after adding this. The same shape
works for Claude Desktop's `claude_desktop_config.json`.

## Alternative: install via pip + git

If you'd rather not clone, you can install directly from git:

```bash
pip install "git+https://github.com/Free-cat/telegram_ads_mcp.git"
playwright install chromium
```

Run `playwright install chromium` **in the same environment/interpreter**
you installed the package into, so the browser binary is available at
runtime. Ephemeral environments (e.g. running via `uvx` on every invocation)
are fragile for this reason — Playwright needs its browser binaries to
persist between runs — which is why the clone + venv path above is
recommended for anything beyond a quick try.

## Tools

All mutating/financial tools default to `confirm=False`, which returns a
structured dry-run preview and makes no changes. Pass `confirm=True` to
actually execute the action.

| Tool | Type | `confirm` required? | Description |
|------|------|----------------------|--------------|
| `list_accounts` | Read | — | List Telegram Ads accounts available for this login session |
| `list_ads` | Read | — | List all ads with full table columns (id, metrics, budget, status, date) |
| `get_ad_info` | Read | — | Read ad form fields (targeting chips are read-only for existing ads) |
| `get_account_budget` | Read | — | Read-only per-ad budgets on `/account/budget` |
| `update_ad` | Write | Yes (to save) | Update ad info fields (title, text, url, budget, etc.), not CPM/budget delta |
| `set_cpm` | Write | Yes (to execute) | Set CPM via the `/edit_cpm` modal |
| `set_status` | Write | Yes (to execute) | Set ad status (Active / On Hold) via the `/edit_status` modal |
| `increase_budget` | Write (financial) | Yes (to execute) | Add TON to an ad's budget (delta) |
| `set_budget` | Write (financial) | Yes (to execute) | Set a target budget by computing the delta from the current one |
| `create_ad` | Write (financial) | Yes (to execute) | Create a new ad; clears the draft by default |
| `get_ad_stats_csv` | Write (download) | Yes (to execute) | Download the stats CSV for an ad and period |

Every tool raises a stable `AUTH_EXPIRED` error when the stored session is no
longer valid — re-run `telegram-ads-auth` to refresh it.

## Configuration

| Env var | Purpose |
|---------|---------|
| `TELEGRAM_ADS_AUTH_STATE` | Absolute path to the saved Playwright session file. Overrides the default lookup (`~/.config/telegram-ads-mcp/auth_state.json`, falling back to `./auth_state.json` in the current directory). |
| `TELEGRAM_ADS_ACCOUNT` | Substring match against the account name shown on the Telegram Ads "Choose Account" screen, used to select which account's ads the tools operate on. Optional when your login has exactly one account; required when multiple accounts are available. |

## Limitations

- **Fragment top-ups are manual.** The server can read per-ad budgets but
  does not automate adding TON via Fragment.
- **Ad Schedule and similar widgets are not automated.** Scheduling and
  "Similar channels/bots" targeting widgets on ads.telegram.org are out of
  scope for v0.1.
- **Targeting on existing ads is read-only.** `get_ad_info` can read
  targeting chips, but changing targeting for an already-created ad is not
  supported — targeting is set at creation time via `create_ad`.
- **No live end-to-end tests in CI.** Tests that hit the real
  ads.telegram.org are marked `live`, require a real session, and are never
  run automatically — they need a human with an active account to run them
  locally.
- **Transport is stdio only.** There is no remote/HTTP transport or Docker
  image in this release.

## License

[MIT](LICENSE)
