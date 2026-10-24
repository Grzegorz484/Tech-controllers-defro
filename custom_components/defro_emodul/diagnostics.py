"""Allowlisted diagnostics without tokens, menu codes or account identifiers."""

from collections import Counter

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import MENU_TYPES, VERSION
from .model import read_entity


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coordinator = entry.runtime_data
    snapshot = coordinator.data or {}
    readings = [read_entity(spec, snapshot) for spec in coordinator.catalogue["entities"]]
    return {
        "integration_version": VERSION,
        "catalogue_entities": len(readings),
        "available_entities": sum(r.available for r in readings),
        "status_counts": dict(Counter(r.reason for r in readings)),
        "controller_online": snapshot.get("online", False),
        "sections": {name: section.get("status") for name, section in snapshot.get("sections", {}).items()},
        "menu_code_present": {name: bool(coordinator.api.menu_codes.get(name)) for name in MENU_TYPES},
    }

