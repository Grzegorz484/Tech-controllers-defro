"""Serve the bundled menu card and register its Lovelace module when possible."""

from pathlib import Path
import logging

from homeassistant.exceptions import HomeAssistantError

from .const import VERSION

CARD_PATH = "/defro_emodul_static/defro-emodul-card.js"
_LOGGER = logging.getLogger(__name__)


async def async_setup_ui(hass):
    if getattr(hass, "http", None) is None:
        return
    from homeassistant.components.http import StaticPathConfig

    if not hass.data.get("defro_emodul_ui_registered"):
        await hass.http.async_register_static_paths([
            StaticPathConfig(CARD_PATH, str(Path(__file__).parent / "www/defro-emodul-card.js"), False)
        ])
        hass.data["defro_emodul_ui_registered"] = True
    lovelace = hass.data.get("lovelace")
    if lovelace is None or lovelace.resource_mode != "storage":
        return
    try:
        resources = lovelace.resources
        await resources.async_get_info()
        url = CARD_PATH + "?v=" + VERSION
        for item in resources.async_items():
            if item.get("url", "").split("?")[0] == CARD_PATH:
                if item["url"] != url:
                    await resources.async_update_item(item["id"], {"url": url, "res_type": "module"})
                return
        await resources.async_create_item({"url": url, "res_type": "module"})
    except (HomeAssistantError, OSError):
        _LOGGER.warning("Dodaj ręcznie zasób Lovelace: %s?v=%s (moduł JavaScript).", CARD_PATH, VERSION)
