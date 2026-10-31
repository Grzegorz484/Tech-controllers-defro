"""Animation metadata for device readings in the bundled overview card."""

from typing import Any

from .icons import icon_for
from .model import read_entity


def tile_activity(
    spec: dict[str, Any], snapshot: dict[str, Any] | None, *, last_update_success: bool
) -> dict[str, Any]:
    """Animate only known device fields with an available, true work flag."""
    icon = icon_for(spec["name"], spec.get("unit"))
    animation, state_field = "", ""
    if spec["section"] == "tile" and not spec.get("diagnostic"):
        element_type, field = spec["element_type"], spec["field"]
        if element_type == 11 and field == "workingStatus":
            animation = {
                "mdi:screw-machine-flat-top": "feed",
                "mdi:heating-coil": "heat",
                "mdi:pump": "pump",
                "mdi:water-boiler": "pump",
            }.get(icon, "")
            state_field = "workingStatus"
        elif element_type == 22 and field in ("gear", "workingStatus"):
            animation, state_field = "fan", "workingStatus"
        elif element_type == 23:
            if field in ("workingStatus", "openingPercentage"):
                animation, state_field = "valve", "workingStatus"
            elif field == "valvePump":
                icon = "mdi:pump"
                animation, state_field = "pump", "valvePump"

    active = False
    if animation and last_update_success and read_entity(spec, snapshot).available:
        state_spec = {**spec, "field": state_field, "transform": "boolean"}
        state = read_entity(state_spec, snapshot)
        active = state.available and state.value is True
    return {"icon": icon, "animation": animation, "active": active}
