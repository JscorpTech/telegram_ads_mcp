def test_package_exports_version():
    import telegram_ads_mcp

    assert telegram_ads_mcp.__version__ == "0.1.0"


def test_client_importable():
    from telegram_ads_mcp.client import TelegramAdsClient

    assert TelegramAdsClient is not None


def test_main_module_has_main():
    from telegram_ads_mcp import mcp_server

    assert callable(mcp_server.main)
