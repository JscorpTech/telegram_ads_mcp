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

## Spend risk — `confirm=true`, and the controls that actually bound it

Every tool that mutates state (`update_ad`, `set_cpm`, `set_status`,
`increase_budget`, `set_budget`, `create_ad`, `get_ad_stats_csv`) defaults to
`confirm=false`, which returns a structured preview and makes **no** network
mutation. Passing `confirm=true` executes the action for real.

`increase_budget`, `set_budget`, and `create_ad` can directly spend TON.

**`confirm` is not an authorization boundary.** It is a flag the *model* sets,
so anything that can put text in front of your agent — a web page it reads, a
tool result, a poisoned description from another server — can in principle
persuade it to pass `confirm=true`. Treat it as a speed bump, not a lock.

The controls that hold are the environment ones, because the model cannot reach
your environment:

| Env var | Effect |
|---------|--------|
| `TELEGRAM_ADS_READ_ONLY=1` | Every tool that changes the account is refused before any I/O, regardless of `confirm`. The read-only tools keep working, including the stats download, so a monitoring-only deployment stays useful. |
| `TELEGRAM_ADS_MAX_SPEND_TON=<n>` | Any single budget increase above `n` TON is refused. Applies to previews as well, so a preview can never promise something the gate would then block. |

Recommended posture:

- Run with `TELEGRAM_ADS_READ_ONLY=1` by default, and unset it only for the
  session where you actually intend to make changes.
- Set `TELEGRAM_ADS_MAX_SPEND_TON` to the largest single change you would ever
  approve by hand.
- Review the preview output before re-calling with `confirm=true`.
- Keep a human in the loop for financial calls. Don't give an unattended agent
  write access to an account you care about.

## Tool annotations are hints, not a security boundary

MCP tool annotations (`read_only_hint`, `destructive_hint`,
`idempotent_hint`, `open_world_hint`) exist so clients can render better
consent UX — warning banners before destructive calls, fewer prompts for
read-only ones. The specification tells clients to treat them as **untrusted**
unless they come from a trusted server, and this server does not enforce them
as access control: any client with a connection can call any tool, subject only
to the gates above.

Note the defaults if you are building on these: `destructive_hint` defaults to
*true* when unset, so a tool that stays silent is advertised as destructive.
This server sets them explicitly per tool.

## Trust boundary: what this server does and does not defend

**In scope** — please report:

- A way to bypass `TELEGRAM_ADS_READ_ONLY` or `TELEGRAM_ADS_MAX_SPEND_TON`.
- A way to make a state-changing call execute while `confirm=false`.
- A way to read `auth_state.json`, or to make the server write it somewhere
  other than the resolved path.
- A way to make the server act on an account other than the selected one.
- Output-injection channels: page content that reaches the model in a form that
  can be mistaken for instructions rather than data.

**Out of scope** — by design, not by oversight:

- **The stdio trust boundary.** A client that can launch this process can
  already run arbitrary code as you; the server does not defend against its own
  launcher. The same is true of every stdio MCP server.
- **Your MCP client's judgement.** If a client offers the model `confirm=true`
  without asking you, that is the client's consent design.
- **ads.telegram.org itself.** The site is authoritative; if it lets a request
  through that you did not want, that is a Telegram issue, not this server's.
- **The account you point it at.** The server holds whatever authority the saved
  session has. It cannot narrow that; only your Telegram account settings can.

## What the server deliberately does not do

These are security-relevant properties, not omissions:

- **It never binds a network port.** Transport is stdio only. There is no HTTP
  listener to reach from a browser, which is what made the MCP Inspector
  CSRF vulnerability (CVE-2025-49596) exploitable.
- **It takes credentials from the environment, not OAuth.** The spec directs
  stdio servers to do exactly this rather than run an authorization flow.
- **It never fetches a URL the model supplies.** Every navigation is
  `https://ads.telegram.org` plus a path built from an integer ad id, so there
  is no server-side request forgery surface.
- **It never evaluates JavaScript in the page**, and uses no `page.evaluate` or
  `add_init_script`; interaction is limited to Playwright locators.
- **It caps untrusted output.** A downloaded stats CSV is truncated with an
  explicit marker rather than being passed through unbounded.
- **It rate limits itself.** Browser calls are serialised and spaced, so a
  looping agent cannot hammer ads.telegram.org.

## Supported versions

Security fixes land on the latest release only. This is a small project; there
are no backport branches.

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes |
| < 0.2   | No — 0.1.0 cannot start against MCP SDK 2.x |

## Reporting a vulnerability

Please use **GitHub's private vulnerability reporting** on this repository's
**Security** tab rather than a public issue. If you cannot, open an issue that
describes the *class* of problem without a working exploit.

Expect an acknowledgement within about a week; this is a volunteer project with
no dedicated security team, so please allow time before following up. We will
credit you in the release notes unless you ask us not to.

Please do not include your real `auth_state.json` contents, account name, or
spend figures in any report. A redacted shape is enough to reproduce almost
everything.
