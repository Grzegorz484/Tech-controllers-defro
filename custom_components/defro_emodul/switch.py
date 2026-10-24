"""Editable on/off menu values and individual checkbox options."""

from homeassistant.components.switch import SwitchEntity

from .control_entity import DefroControl, setup_controls

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    setup_controls(entry, async_add_entities, {"switch", "checkbox_option"}, DefroSwitch)


class DefroSwitch(DefroControl, SwitchEntity):
    @property
    def is_on(self):
        return self.reading.value

    async def async_turn_on(self, **kwargs):
        await self.async_write(True)

    async def async_turn_off(self, **kwargs):
        await self.async_write(False)
