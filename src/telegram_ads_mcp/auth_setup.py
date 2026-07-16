#!/usr/bin/env python3
"""One-time auth setup: log in manually, pick account, save session."""

from __future__ import annotations

from playwright.sync_api import sync_playwright

from telegram_ads_mcp.paths import ensure_secure_file, resolve_auth_state_path

BASE_URL = "https://ads.telegram.org/"


def main() -> None:
    auth_path = resolve_auth_state_path()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(BASE_URL)
        print("1) Log in via Telegram in the browser.")
        print("2) On Choose Account — open the account you want (e.g. Personal / Artem).")
        print("3) Wait until you see the ads table at /account.")
        input("Then press Enter here to save the session...")
        if "choose_account" in page.url:
            print("WARNING: still on choose_account — pick an account first, then re-run.")
        context.storage_state(path=str(auth_path))
        browser.close()
    ensure_secure_file(auth_path)
    print(f"Session saved to {auth_path}")


if __name__ == "__main__":
    main()
