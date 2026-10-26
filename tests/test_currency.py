import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_ads_mcp.client import TelegramAdsClient


def make_form(currency):
    page = MagicMock()
    field = MagicMock()
    field.count = AsyncMock(return_value=1)
    field.is_visible = AsyncMock(return_value=True)
    field.fill = AsyncMock()
    field.click = AsyncMock()
    field.check = AsyncMock()
    field.first = field
    field.filter.return_value = field
    field.locator.return_value = field
    field.get_by_role.return_value = field
    page.locator.return_value = field
    page.get_by_placeholder.return_value = field
    page.get_by_label.return_value = field
    page.get_by_role.return_value = field

    def text(label, **kwargs):
        node = MagicMock()
        node.is_visible = AsyncMock(return_value=bool(label.search(f'CPM in {currency} Price per 1000 impressions.')))
        return node

    page.get_by_text.side_effect = text
    page.wait_for_url = AsyncMock()
    page.url = 'https://ads.telegram.org/account/ad/42'
    client = TelegramAdsClient.__new__(TelegramAdsClient)
    client._lock = asyncio.Lock()
    client._goto = AsyncMock(return_value=page)
    client._read_validation_errors = AsyncMock(return_value=[])
    return client, page, field


@pytest.mark.parametrize('label,code', [('Euro', 'EUR'), ('Ton', 'TON')])
def test_currency_form_read_is_nonmutating(label, code):
    client, _, field = make_form(label)
    result = asyncio.run(client.get_create_ad_form())
    assert result['currency'] == code
    field.fill.assert_not_called()
    field.click.assert_not_called()


def test_mismatched_currency_stops_before_editing():
    client, _, field = make_form('Euro')
    with pytest.raises(ValueError, match='Currency mismatch'):
        asyncio.run(client.create_ad(title='test', text='text', url='t.me/test',
                                   cpm=.2, initial_budget=1, currency='TON', confirm=True))
    field.fill.assert_not_called()
    field.click.assert_not_called()


def test_unknown_currency_fails_closed():
    client, _, field = make_form('Stars')
    with pytest.raises(ValueError, match='Unsupported'):
        asyncio.run(client.get_create_ad_form())
    field.fill.assert_not_called()


def test_eur_create_uses_named_budget_field_and_returns_currency():
    client, page, field = make_form('Euro')
    result = asyncio.run(client.create_ad(title='test', text='text', url='t.me/test',
                                        cpm=.2, initial_budget=1, currency='EUR',
                                        status='On Hold', confirm=True, clear_draft=False))
    assert result == {'ok': True, 'ad_id': 42, 'title': 'test', 'currency': 'EUR'}
    page.locator.assert_any_call('input[name="cpm"]')
    page.locator.assert_any_call('input[name="budget"]')
    field.fill.assert_any_await('1')


def test_eur_dry_run_does_not_open_form():
    client, _, _ = make_form('Euro')
    result = asyncio.run(client.create_ad(title='test', text='text', url='t.me/test',
                                        cpm=.2, initial_budget=1, currency='EUR'))
    assert result['dry_run'] is True
    assert result['currency'] == 'EUR'
    client._goto.assert_not_called()
