#!/usr/bin/env python3
"""One-time auth setup: log in manually, pick an account, save the session."""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

from telegram_ads_mcp.paths import ensure_secure_file, resolve_auth_state_path

BASE_URL = "https://ads.telegram.org/"

_ACCOUNT_HINT = """\
1) Log in via Telegram in the browser window that just opened.
2) On the Choose Account screen, open the account you want this server to manage.
3) Wait until you can see the ads table at ads.telegram.org/account.

Then press Enter here to save the session."""

_STILL_CHOOSING = """\
Still on the Choose Account screen.

A session saved from here will not let the server pick an account, so nothing
was written. Open the account you want in the browser, wait for its ads table
to load, then run `telegram-ads-auth` again.
"""

_NOT_LOGGED_IN = """\
This does not look like a logged-in ads.telegram.org page (url: {url}).

Nothing was written. Finish logging in (including any 2FA prompt) until the ads
table is visible, then run `telegram-ads-auth` again.
"""


def main() -> None:
    auth_path = resolve_auth_state_path()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(BASE_URL)
        print(_ACCOUNT_HINT)
        input()
        url = page.url

        # Refuse to save a session that cannot actually be used. Saving a
        # half-authenticated state produces confusing AUTH_EXPIRED failures
        # later, far from the step that caused them.
        if "choose_account" in url:
            print(_STILL_CHOOSING, file=sys.stderr)
            browser.close()
            raise SystemExit(1)
        if "ads.telegram.org" not in url:
            print(_NOT_LOGGED_IN.format(url=url), file=sys.stderr)
            browser.close()
            raise SystemExit(1)

        context.storage_state(path=str(auth_path))
        browser.close()

    ensure_secure_file(auth_path)
    print(f"Session saved to {auth_path}")
    print("This file is credential-equivalent: keep it out of version control.")


if __name__ == "__main__":
    main()
