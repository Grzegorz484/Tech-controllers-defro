"""Read-only relay states and menu flags."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import DefroEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        DefroBinarySensor(coordinator, spec)
        for spec in coordinator.catalogue["entities"] if spec["platform"] == "binary_sensor"
    ])


class DefroBinarySensor(DefroEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool | None:
        value = self.reading.value
        return value if isinstance(value, bool) else None

