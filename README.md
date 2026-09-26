<!-- mcp-name: io.github.Free-cat/telegram-ads-mcp -->
# telegram-ads-mcp

An [MCP](https://modelcontextprotocol.io) server that lets AI agents (Cursor,
Claude Desktop, Claude Code, etc.) read and manage your
[Telegram Ads](https://ads.telegram.org) campaigns — list accounts and ads,
read stats and budgets, and create/update ads, CPM, status, and budget — by
driving the real ads.telegram.org web UI through Playwright with a reused,
cookie-based login session.

> **⚠️ Security warning**
>
> This server reuses a saved Telegram Ads browser session
> (`auth_state.json`). That file is equivalent to your login credentials for
> ads.telegram.org — anyone with it can act as you, **including spending your
> TON ad budget**. Never commit it, share it, or check it into version
> control. Read [SECURITY.md](SECURITY.md) before connecting this server to any
> agent you don't fully trust with your ad spend.

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

### Alternative: `uv tool install`

`uv tool install` gives you a stable `telegram-ads-mcp` on your `PATH` without
cloning. Install the browser into the tool's own environment so it survives
`uv cache clean`:

```bash
uv tool install telegram-ads-mcp
PLAYWRIGHT_BROWSERS_PATH=0 uv tool run --from telegram-ads-mcp playwright install --only-shell chromium
telegram-ads-auth
```

`PLAYWRIGHT_BROWSERS_PATH=0` keeps Chromium inside the tool's virtualenv rather
than a shared cache, and `--only-shell` skips the headed browser — this server
runs headless.

Plain `uvx telegram-ads-mcp` on every invocation is **not** recommended:
`uvx` rebuilds an ephemeral environment, which is discarded by `uv cache
clean`, taking the browser binaries with it.

## Client configuration

### Claude Code

```bash
claude mcp add telegram-ads \
  --env TELEGRAM_ADS_ACCOUNT=YourAccountName \
  -- /ABS/PATH/telegram_ads_mcp/.venv/bin/telegram-ads-mcp
```

Add `--scope user` to make it available in every project. `claude mcp list`
verifies it connected.

### Claude Desktop

Edit `claude_desktop_config.json` (`~/Library/Application Support/Claude/` on
macOS, `%APPDATA%\Claude\` on Windows):

```json
{
  "mcpServers": {
    "telegram-ads": {
      "command": "/ABS/PATH/telegram_ads_mcp/.venv/bin/telegram-ads-mcp",
      "env": {
        "TELEGRAM_ADS_ACCOUNT": "YourAccountName",
        "TELEGRAM_ADS_AUTH_STATE": "/ABS/PATH/to/auth_state.json"
      }
    }
  }
}
```

On Windows, wrap the command as `cmd /c` with `.venv\Scripts\telegram-ads-mcp.exe`.

### Cursor

Same shape, in `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project):

```json
{
  "mcpServers": {
    "telegram-ads": {
      "command": "/ABS/PATH/telegram_ads_mcp/.venv/bin/telegram-ads-mcp",
      "env": {
        "TELEGRAM_ADS_ACCOUNT": "YourAccountName"
      }
    }
  }
}
```

### VS Code

`.vscode/mcp.json` uses a `servers` key rather than `mcpServers`:

```json
{
  "servers": {
    "telegram-ads": {
      "type": "stdio",
      "command": "/ABS/PATH/telegram_ads_mcp/.venv/bin/telegram-ads-mcp"
    }
  }
}
```

Use an **absolute** path to the console script — GUI clients do not inherit
your shell's `PATH`. Restart the client (or reload MCP servers) after editing.

## Tools

Mutating tools default to `confirm=false`, which returns a structured preview
of exactly what would happen and touches nothing. Pass `confirm=true` to
execute. Read-only tools take no `confirm` argument.

Every tool returns structured content (`structuredContent`) alongside a text
rendering, so clients can parse results programmatically rather than reading
prose.

| Tool | Access | Changes | `confirm` | Description |
|------|--------|---------|-----------|-------------|
| `list_accounts` | Read | — | — | List the accounts available to this login session |
| `list_ads` | Read | — | — | List all ads with metrics, budget, status and date |
| `get_ad_info` | Read | — | — | Read one ad's form fields and settings |
| `get_account_budget` | Read | — | — | Read the balance and transaction ledger |
| `get_ad_stats_csv` | Read | Downloads a CSV | Yes | Download stats for an ad and period |
| `update_ad` | Write | Edits ad fields | Yes | Update title, text, URL, daily budget, status, etc. |
| `set_cpm` | Write | Edits CPM | Yes | Set CPM via the `/edit_cpm` modal |
| `set_status` | Write | Pauses/resumes | Yes | Set status to Active or On Hold |
| `increase_budget` | Write | **Spends TON** | Yes | Add TON to an ad's budget |
| `set_budget` | Write | **Spends TON** | Yes | Set a target budget by adding the difference |
| `create_ad` | Write | **Spends TON** | Yes | Create and fund a new ad |

Every tool returns a stable error `code` when something anticipated goes wrong.
`AUTH_EXPIRED` means the stored session is gone or rejected — re-run
`telegram-ads-auth`.

## Safety controls

The `confirm` flag is a decision the *model* makes, so it is not an
authorization boundary: anything that can instruct your agent can ask it to
pass `confirm=true`. The controls below come from the environment, which the
model cannot reach.

| Env var | Effect |
|---------|--------|
| `TELEGRAM_ADS_READ_ONLY=1` | Refuse every tool that changes the account, whatever `confirm` says. Read-only tools — including the stats download — keep working. |
| `TELEGRAM_ADS_MAX_SPEND_TON=5` | Refuse any single budget increase above this many TON. Applies to previews too. |

Set `TELEGRAM_ADS_READ_ONLY=1` when you want an agent to monitor campaigns
without any possibility of it changing them.

## Configuration

| Env var | Purpose |
|---------|---------|
| `TELEGRAM_ADS_AUTH_STATE` | Absolute path to the saved Playwright session file. Overrides the default lookup (`~/.config/telegram-ads-mcp/auth_state.json`, falling back to `./auth_state.json` in the current directory). |
| `TELEGRAM_ADS_ACCOUNT` | Substring match against the account name shown on the "Choose Account" screen, used to select which account's ads the tools operate on. Optional when your login has exactly one account; required when multiple accounts are available. |
| `TELEGRAM_ADS_READ_ONLY` | See [Safety controls](#safety-controls). |
| `TELEGRAM_ADS_MAX_SPEND_TON` | See [Safety controls](#safety-controls). |

## Limitations

- **Fragment top-ups are manual.** The server can read per-ad budgets but
  does not automate adding TON via Fragment.
- **Ad Schedule and similar widgets are not automated.** Scheduling and
  "Similar channels/bots" targeting widgets on ads.telegram.org are out of
  scope.
- **Targeting on existing ads is read-only.** `get_ad_info` can read
  targeting chips, but changing targeting for an already-created ad is not
  supported — targeting is set at creation time via `create_ad`.
- **One account per process.** The account is chosen when the server starts
  from `TELEGRAM_ADS_ACCOUNT`; there is no tool to switch accounts mid-session.
- **Transport is stdio only, and deliberately so.** There is no remote/HTTP
  transport or Docker image: a local subprocess never binds a network port,
  and the spec directs stdio servers to take credentials from the environment
  rather than running an authorization flow.
- **No live end-to-end tests in CI.** Tests that hit the real
  ads.telegram.org are marked `live`, require a real session, and are never
  run automatically — they need a human with an active account to run them
  locally.

## Development

```bash
pip install -e ".[dev]"
ruff check src tests && ruff format --check src tests
pyright
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)