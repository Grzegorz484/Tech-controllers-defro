from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.defro_emodul.frontend import CARD_PATH,async_setup_ui
from custom_components.defro_emodul.const import VERSION


@pytest.mark.parametrize('old_url',[None,CARD_PATH+'?v=1.0.0',CARD_PATH+'?v=1.1.0'])
async def test_card_resource_is_registered_once_and_versioned(hass,monkeypatch,old_url):
    static=AsyncMock()
    monkeypatch.setattr(hass,'http',SimpleNamespace(async_register_static_paths=static),raising=False)
    items=[] if old_url is None else [{'id':'resource','url':old_url,'type':'module'}]
    async def create(data):items.append({'id':'resource','url':data['url'],'type':data['res_type']})
    async def update(item_id,data):items[0]['url']=data['url']
    resources=SimpleNamespace(async_get_info=AsyncMock(),async_items=lambda:items,
                              async_create_item=AsyncMock(side_effect=create),async_update_item=AsyncMock(side_effect=update))
    hass.data['lovelace']=SimpleNamespace(resource_mode='storage',resources=resources)
    await async_setup_ui(hass)
    await async_setup_ui(hass)
    assert static.await_count==1
    config=static.call_args.args[0][0]
    assert config.url_path==CARD_PATH and Path(config.path).is_file()
    assert len(items)==1 and items[0]['url']==CARD_PATH+'?v='+VERSION
    assert resources.async_create_item.await_count==(old_url is None)
    assert resources.async_update_item.await_count==(old_url is not None)


async def test_yaml_resource_configuration_is_respected(hass,monkeypatch):
    monkeypatch.setattr(hass,'http',SimpleNamespace(async_register_static_paths=AsyncMock()),raising=False)
    resources=SimpleNamespace(async_create_item=AsyncMock())
    hass.data['lovelace']=SimpleNamespace(resource_mode='yaml',resources=resources)
    await async_setup_ui(hass)
    resources.async_create_item.assert_not_called()
