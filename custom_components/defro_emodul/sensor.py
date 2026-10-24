"""Read-only numeric, status, schedule and setting sensors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import DefroEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        DefroSensor(coordinator, spec)
        for spec in coordinator.catalogue["entities"] if spec["platform"] == "sensor"
    ])


class DefroSensor(DefroEntity, SensorEntity):
    def __init__(self, coordinator, spec: dict) -> None:
        super().__init__(coordinator, spec)
        self._attr_native_unit_of_measurement = spec.get("unit")
        if spec.get("unit") == "°C":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        elif spec.get("unit") in ("s", "min", "h"):
            self._attr_device_class = SensorDeviceClass.DURATION
        if spec["section"] == "tile" and spec["transform"] == "number" and spec.get("unit") in ("°C", "%"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if spec["transform"] == "number" and spec.get("divisor") == 10:
            self._attr_suggested_display_precision = 1

    @property
    def native_value(self):
        return self.reading.value

