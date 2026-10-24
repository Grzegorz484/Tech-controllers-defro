import json
from pathlib import Path
import sys

import pytest
import pytest_asyncio
import aiohttp

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant import loader
from homeassistant.helpers import entity_registry,device_registry,area_registry,floor_registry,label_registry,issue_registry,restore_state


@pytest.fixture
def catalogue():
    return json.loads((PROJECT / 'custom_components/defro_emodul/catalogue.json').read_text())


@pytest.fixture
def snapshot():
    result=json.loads((PROJECT/'tests/fixtures/snapshot.json').read_text(encoding='utf-8'))
    for section in result['sections'].values():
        section['elements']={int(key):value for key,value in section['elements'].items()}
    return result


@pytest_asyncio.fixture
async def hass(tmp_path,monkeypatch):
    config = tmp_path / 'ha';config.mkdir()
    (config / 'custom_components').symlink_to(PROJECT / 'custom_components',target_is_directory=True)
    instance = HomeAssistant(str(config))
    loader.async_setup(instance)
    device_registry.async_setup(instance)
    for registry in (floor_registry,label_registry,area_registry,device_registry,entity_registry,issue_registry,restore_state):
        await registry.async_load(instance)
    instance.config_entries = ConfigEntries(instance,{})
    await instance.config_entries.async_initialize()
    session=aiohttp.ClientSession()
    # A real session is injected; no mDNS/network integration is needed in the test HA.
    monkeypatch.setattr('custom_components.defro_emodul.async_get_clientsession',lambda hass:session)
    monkeypatch.setattr('custom_components.defro_emodul.config_flow.async_get_clientsession',lambda hass:session)
    yield instance
    for entry in instance.config_entries.async_entries('defro_emodul'):
        await instance.config_entries.async_unload(entry.entry_id)
    await instance.async_stop(force=True)
    await session.close()

