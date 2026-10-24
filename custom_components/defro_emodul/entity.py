"""Common entity properties and availability."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DefroCoordinator
from .model import Reading, read_entity
from .icons import icon_for


class DefroEntity(CoordinatorEntity[DefroCoordinator]):
    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = True
    _attr_should_poll = False

    def __init__(self, coordinator: DefroCoordinator, spec: dict) -> None:
        super().__init__(coordinator)
        self.spec = spec
        self._attr_name = spec["name"]
        self._attr_icon = icon_for(spec["name"], spec.get("unit"))
        self._attr_unique_id = coordinator.udid + ":" + spec["key"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.udid)},
            manufacturer="DEFRO", model="APC Slim / ST-9730",
            name=coordinator.device_title,
            sw_version=(coordinator.data or {}).get("metadata", {}).get("version") or coordinator.catalogue.get("source_firmware"),
        )
        if spec.get("diagnostic"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def suggested_object_id(self) -> str:
        """Suggest stable source keys; HA preserves user registry renames."""
        return "defro_" + self.spec["key"]

    @property
    def reading(self) -> Reading:
        return read_entity(self.spec, self.coordinator.data)

    @property
    def available(self) -> bool:
        return super().available and self.reading.available

    @property
    def extra_state_attributes(self) -> dict:
        reading = self.reading
        return {**(reading.attributes or {}), "read_status": reading.reason}

