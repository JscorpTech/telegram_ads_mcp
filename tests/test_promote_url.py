import asyncio
from unittest.mock import AsyncMock
import pytest
from test_currency import make_form

def test_uses_named_promote_url_not_dynamic_placeholder():
 c,p,f=make_form('Euro');f.wait_for=AsyncMock();f.input_value=AsyncMock(return_value='https://t.me/venu_market')
 r=asyncio.run(c.create_ad(title='test',text='text',url='https://t.me/venu_market',cpm=.2,initial_budget=1,currency='EUR',status='On Hold',confirm=True,clear_draft=False))
 assert r['ad_id']==42
 p.locator.assert_any_call('input[name="promote_url"]')
 assert not any(call.args[0]=='URL of the channel, post or bot you promote' for call in p.get_by_placeholder.call_args_list)

def test_url_mismatch_never_submits():
 c,p,f=make_form('Euro');f.wait_for=AsyncMock();f.input_value=AsyncMock(return_value='https://t.me/wrong')
 with pytest.raises(RuntimeError,match='no ad submitted'):
  asyncio.run(c.create_ad(title='test',text='text',url='https://t.me/venu_market',cpm=.2,initial_budget=1,currency='EUR',confirm=True,clear_draft=False))
 assert not any(call.args[0]=="button" for call in p.get_by_role.call_args_list)
