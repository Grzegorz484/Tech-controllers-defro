"""Editable operating modes and choices supplied by the controller."""

from homeassistant.components.select import SelectEntity

from .control_entity import DefroControl, setup_controls

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    setup_controls(entry, async_add_entities, {"select"}, DefroSelect)


class DefroSelect(DefroControl, SelectEntity):
    @property
    def options(self):
        return [o["label"] for o in self.info.get("options", [])]

    @property
    def current_option(self):
        return next((o["label"] for o in self.info.get("options", []) if o["value"] == self.info.get("value")), None)

    async def async_select_option(self, option):
        await self.async_write(option)
