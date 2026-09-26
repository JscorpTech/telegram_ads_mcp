import re
from pathlib import Path


def test_package_exports_version():
    import telegram_ads_mcp

    assert re.fullmatch(r"\d+\.\d+\.\d+", telegram_ads_mcp.__version__)


def test_pyproject_does_not_hardcode_a_second_version():
    """The version is single-sourced from `__init__.py` via hatchling.

    Two sources drift silently: the wheel would report one version while the
    server told clients another.
    """
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text()
    assert 'dynamic = ["version"]' in text
    assert "[tool.hatch.version]" in text
    assert not re.search(r'^version = "', text, flags=re.MULTILINE)


def test_client_importable():
    from telegram_ads_mcp.client import TelegramAdsClient

    assert TelegramAdsClient is not None


def test_main_module_has_main():
    from telegram_ads_mcp import mcp_server

    assert callable(mcp_server.main)
