import pytest

from telegram_ads_mcp.client import choose_account
from telegram_ads_mcp.exceptions import AccountSelectionError
from telegram_ads_mcp.models import Account


def _acc(name: str, token: str = "t") -> Account:
    return Account(name=name, token=token, href=f"/choose_account/{token}")


def test_choose_account_by_preferred_name():
    accounts = [_acc("Personal"), _acc("Work", "w")]
    assert choose_account(accounts, "work") == accounts[1]


def test_choose_account_auto_select_single():
    accounts = [_acc("Only One")]
    assert choose_account(accounts, None) == accounts[0]


def test_choose_account_requires_env_when_multiple():
    accounts = [_acc("Personal"), _acc("Work", "w")]
    with pytest.raises(AccountSelectionError, match="TELEGRAM_ADS_ACCOUNT is not set"):
        choose_account(accounts, None)


def test_choose_account_lists_available_on_mismatch():
    accounts = [_acc("Personal"), _acc("Work", "w")]
    with pytest.raises(AccountSelectionError, match="not found. Available: Personal, Work"):
        choose_account(accounts, "Missing")


def test_choose_account_empty_list():
    with pytest.raises(AccountSelectionError, match="No accounts available"):
        choose_account([], None)


def test_errors_render_with_a_code():
    """The message reaches a model, which needs the code to branch on."""
    with pytest.raises(AccountSelectionError) as excinfo:
        choose_account([], None)
    assert str(excinfo.value).startswith("ACCOUNT_SELECTION: ")
