from telegram_ads_mcp.parsing import extract_ad_id, parse_decimal, parse_int_commas


def test_parse_int_commas():
    assert parse_int_commas("10,788") == 10788
    assert parse_int_commas("-") == 0


def test_parse_decimal_strips_currency():
    assert parse_decimal("💎0.20") == 0.2
    assert parse_decimal("–") == 0.0


def test_extract_ad_id():
    assert extract_ad_id("/account/ad/3/stats") == 3
    assert extract_ad_id("https://ads.telegram.org/account/ad/7") == 7
    assert extract_ad_id("/choose_account/x") is None


def test_missing_metric_unicode_dashes():
    for value in ('–', '—', '-'):
        assert parse_int_commas(value) == 0
