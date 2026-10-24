"""DEFRO eModuł, read-only entities for the supplied ST-9730 catalogue."""

import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .api import Authentication, EmodulApi
from .const import CONF_MENU_CODES, CONF_SITE, CONF_USER_ID, DOMAIN
from .coordinator import DefroCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def load_catalogue() -> dict:
    with Path(__file__).with_name("catalogue.json").open(encoding="utf-8") as stream:
        return json.load(stream)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    catalogue = await hass.async_add_executor_job(load_catalogue)
    api = EmodulApi(
        async_get_clientsession(hass), entry.data[CONF_SITE],
        Authentication(str(entry.data[CONF_USER_ID]), entry.data[CONF_TOKEN]),
        menu_codes=entry.data.get(CONF_MENU_CODES, {}),
        fallback_texts=catalogue.get("texts", {}),
    )
    coordinator = DefroCoordinator(hass, entry, api, catalogue)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

