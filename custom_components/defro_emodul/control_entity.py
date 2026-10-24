"""Shared live discovery for editable menu entities."""

from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .entity import DefroEntity
from .model import Reading


def setup_controls(entry, async_add_entities, kinds, entity_class):
    coordinator = entry.runtime_data
    seen = set()
    units = {(s["section"], s["element_id"]): s.get("unit") for s in coordinator.catalogue["entities"]}

    @callback
    def discover():
        entities = []
        for info in coordinator.controls.values():
            if info["kind"] not in kinds or info["key"] in seen:
                continue
            spec = {**info, "unit": info.get("unit") or units.get((info["section"], info["id"]))}
            seen.add(info["key"])
            entities.append(entity_class(coordinator, spec))
        async_add_entities(entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class DefroControl(DefroEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, spec):
        super().__init__(coordinator, spec)
        self._attr_unique_id = coordinator.udid + ":control:" + spec["key"]
        self._attr_icon = spec["icon"]

    @property
    def suggested_object_id(self):
        return "defro_ustaw_" + self.spec["key"]

    @property
    def info(self):
        return self.coordinator.controls.get(self.spec["key"], {})

    @property
    def reading(self):
        info = self.info
        return Reading(value=info.get("value"), available=bool(info.get("available")),
                       reason=info.get("reason", "not_loaded"))

    @property
    def extra_state_attributes(self):
        base = self.info.get("base_key", self.spec["key"])
        return {"write_status": self.reading.reason,
                "write_warning": self.coordinator.write_errors.get(base)}

    async def async_write(self, value):
        await self.coordinator.async_write_control(self.spec["key"], value)
