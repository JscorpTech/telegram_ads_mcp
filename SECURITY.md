# Security Policy

## Session file is a secret

`auth_state.json` (the Playwright storage state file produced by `telegram-ads-auth`)
contains your live Telegram Ads session cookies and local storage. Anyone who
has this file can act as you on [ads.telegram.org](https://ads.telegram.org) —
including spending your TON budget — without needing your password or 2FA.

Treat it exactly like a password or API key:

- **Never commit it** to git, paste it in chat, upload it to an issue, or share it
  in any support request. The repository's `.gitignore` already excludes
  `auth_state.json` and `**/auth_state.json`, but double-check before pushing
  forks or mirrors.
- Store it outside the repo when possible (the default path is
  `~/.config/telegram-ads-mcp/auth_state.json`; override with
  `TELEGRAM_ADS_AUTH_STATE`).
- The tool attempts to create/update this file with `0600` permissions
  (owner read/write only) via `ensure_secure_file`. Verify this on your system:

  ```bash
  ls -l ~/.config/telegram-ads-mcp/auth_state.json
  # -rw------- ... auth_state.json
  ```

  If permissions are looser (e.g. copied via a tool that doesn't preserve
  modes, or on a filesystem that doesn't support POSIX permissions), fix them
  manually with `chmod 600 <path>`.

## Revoking a session

If you believe `auth_state.json` has been exposed, or you simply want to
rotate credentials:

1. Delete the local file:

   ```bash
   rm ~/.config/telegram-ads-mcp/auth_state.json
   ```

2. Log out of the session on Telegram's side by visiting
   [ads.telegram.org](https://ads.telegram.org), opening the account menu, and
   choosing **Log Out**. This invalidates the underlying Telegram session so
   the old `auth_state.json` (even if a copy exists elsewhere) can no longer
   be used.
3. Re-run `telegram-ads-auth` to generate a fresh session when you need to use
   the server again.

## Spend risk — `confirm=True`

Every tool that mutates state (`update_ad`, `set_cpm`, `set_status`,
`increase_budget`, `set_budget`, `create_ad`, `get_ad_stats_csv`) defaults to
`confirm=False`, which returns a structured dry-run preview and makes **no**
network mutation. Passing `confirm=True` executes the action for real.

`increase_budget`, `set_budget`, and `create_ad` can directly spend TON from
your Telegram Ads account. Before letting an AI agent call these tools with
`confirm=True`:

- Understand that the agent (or anything that can send it instructions) can
  spend your ad budget once it is allowed to pass `confirm=True`.
- Review the dry-run output first; it mirrors exactly what the real call would
  do.
- Don't grant an untrusted or automated agent unattended write access —
  keep a human in the loop for `confirm=True` calls, especially financial ones.

## Tool annotations are hints, not a security boundary

MCP tool annotations (`readOnlyHint`, `destructiveHint`, `openWorldHint`) are
provided so MCP clients can render better UX (e.g. warning banners before
destructive calls). They are **not** enforced by this server as an access
control mechanism — any client with a connection to the server can call any
tool, subject only to the `confirm=True` gate described above. Don't rely on
annotations alone to prevent an agent from taking an action; rely on the
`confirm` gate and your own review process.

## Reporting a vulnerability

This is a small, community-maintained project with no dedicated security
team. If you find a vulnerability (e.g. a way to bypass the `confirm` gate,
leak `auth_state.json` contents, or execute unintended requests), please open
a GitHub issue on this repository, or, if the issue is sensitive, use
GitHub's private vulnerability reporting feature on the repo's **Security**
tab. Please do not include your own real `auth_state.json` contents or
account details in any report.
