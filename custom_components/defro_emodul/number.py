"""Editable numeric settings and heating-curve points."""

from homeassistant.components.number import NumberEntity, NumberMode

from .control_entity import DefroControl, setup_controls

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    setup_controls(entry, async_add_entities, {"number", "curve_point"}, DefroNumber)


class DefroNumber(DefroControl, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec)
        self._attr_native_unit_of_measurement = "°C" if spec["kind"] == "curve_point" else spec.get("unit")

    @property
    def native_value(self):
        return self.reading.value

    @property
    def native_min_value(self):
        return self.info.get("min", 0)

    @property
    def native_max_value(self):
        return self.info.get("max", 100)

    @property
    def native_step(self):
        return self.info.get("step", 1)

    async def async_set_native_value(self, value):
        await self.async_write(value)
