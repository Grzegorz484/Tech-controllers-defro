"""Administrator services used by the full eModul-style menu card."""

import voluptuous as vol

from homeassistant.core import SupportsResponse
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN
from .model import read_entity
from .icons import icon_for


def async_setup_services(hass):
    if hass.services.has_service(DOMAIN, "get_controls"):
        return

    def entries(entry_id=None):
        return [e for e in hass.config_entries.async_entries(DOMAIN)
                if (entry_id is None or e.entry_id == entry_id) and e.state is ConfigEntryState.LOADED and hasattr(e, "runtime_data")]

    async def get_controls(call):
        controllers = []
        registry = er.async_get(hass)
        for entry in entries(call.data.get("entry_id")):
            co = entry.runtime_data
            tiles = []
            for spec in co.catalogue["entities"]:
                if spec["section"] != "tile":
                    continue
                reading = read_entity(spec, co.data)
                tiles.append({"key": spec["key"], "name": spec["name"], "unit": spec.get("unit"),
                              "entity_id": registry.async_get_entity_id(spec["platform"], DOMAIN, co.udid + ":" + spec["key"]),
                              "value": reading.value if reading.available and co.last_update_success else None,
                              "icon": icon_for(spec["name"], spec.get("unit"))})
            controls = [{**i, "warning": co.write_errors.get(i["key"])}
                        for i in co.controls.values() if "base_key" not in i]
            if not co.last_update_success:
                for info in controls:
                    info.update(available=False, can_unlock=False, reason="cloud_unavailable")
            controllers.append({"entry_id": entry.entry_id, "name": entry.title,
                                "online": bool(co.last_update_success and co.data and co.data.get("online")),
                                "controls": controls, "tiles": tiles})
        return {"controllers": controllers}

    async def set_parameter(call):
        targets = entries(call.data["entry_id"])
        if len(targets) != 1:
            raise HomeAssistantError("Wybierz skonfigurowany sterownik DEFRO.")
        await targets[0].runtime_data.async_write_control(
            call.data["key"], call.data["value"], confirm=call.data.get("confirm", False))

    async def unlock_menu(call):
        targets = entries(call.data["entry_id"])
        if len(targets) != 1:
            raise HomeAssistantError("Wybierz skonfigurowany sterownik DEFRO.")
        await targets[0].runtime_data.async_unlock_code(call.data["key"], call.data["code"])

    async_register_admin_service(hass, DOMAIN, "get_controls", get_controls,
                                schema=vol.Schema({vol.Optional("entry_id"): str}),
                                supports_response=SupportsResponse.ONLY)
    async_register_admin_service(hass, DOMAIN, "set_parameter", set_parameter,
                                schema=vol.Schema({vol.Required("entry_id"): str,
                                                   vol.Required("key"): str,
                                                   vol.Required("value"): object,
                                                   vol.Optional("confirm", default=False): bool}))
    async_register_admin_service(hass, DOMAIN, "unlock_menu", unlock_menu,
                                schema=vol.Schema({vol.Required("entry_id"): str,
                                                   vol.Required("key"): str,
                                                   vol.Required("code"): vol.Match(r"^[0-9]{1,16}$")}))
