"""Pure, tested mapping from live payloads to the 317 entity definitions."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class Reading:
    value: Any = None
    available: bool = False
    reason: str = "not_loaded"
    attributes: dict[str, Any] | None = None


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _changing(value: Any) -> bool:
    return value is True or str(value).lower() in ("t", "true", "1")


def _parents(item: dict[str, Any], elements: dict[int, Any]) -> tuple[bool, int | None]:
    seen, current = set(), item
    while isinstance(current, dict):
        current_id, parent_id = current.get("id"), current.get("parentId")
        if parent_id is None or parent_id == current_id:
            return False, None
        if current_id in seen:
            return False, parent_id
        seen.add(current_id)
        parent = elements.get(parent_id)
        if parent is None:
            return False, parent_id
        if parent.get("access") is False:
            return True, None
        current = parent
    return False, None


def _safe_values(value: Any, depth: int = 0) -> Any:
    """Schedules only: cap attributes and omit credential-like keys."""
    if depth > 8:
        return None
    if isinstance(value, list):
        return [_safe_values(x, depth + 1) for x in value[:500]]
    if isinstance(value, dict):
        return {
            str(k): _safe_values(v, depth + 1)
            for k, v in value.items()
            if not any(word in str(k).lower() for word in ("password", "token", "secret", "pin"))
        }
    return value if isinstance(value, (str, int, float, bool, type(None))) else None


def read_entity(spec: dict[str, Any], snapshot: dict[str, Any] | None) -> Reading:
    """Use only live state; the catalogue contains no cached measurements."""
    if not snapshot:
        return Reading()
    if not snapshot.get("online", False):
        return Reading(reason="controller_offline")
    section = snapshot.get("sections", {}).get(spec["section"], {})
    if section.get("status") != "ok":
        return Reading(reason="section_" + str(section.get("status", "missing")))
    elements = section.get("elements", {})
    item = elements.get(spec["element_id"])
    if not isinstance(item, dict):
        return Reading(reason="element_missing")
    if item.get("type") != spec["element_type"]:
        return Reading(reason="schema_changed")
    access = item.get("visibility") if spec["section"] == "tile" else item.get("access")
    if access is False:
        return Reading(reason="api_access_false")
    blocked, missing_parent = _parents(item, elements) if spec["section"] != "tile" else (False, None)
    if blocked:
        return Reading(reason="parent_access_false")
    if _changing(item.get("duringChange")):
        return Reading(reason="value_updating")
    params = item.get("params")
    if not isinstance(params, dict):
        return Reading(reason="parameters_missing")
    attrs = {
        "api_section": spec["section"], "api_id": spec["element_id"],
        "api_field": spec["field"], "api_type": spec["element_type"],
    }
    if missing_parent is not None:
        attrs["missing_parent"] = missing_parent
    field, kind = spec["field"], spec["transform"]
    if "point_position" in spec:
        point = next((p for p in params.get("points", []) if isinstance(p, dict) and p.get("position") == spec["point_position"]), None)
        raw = point.get("value") if point is not None else None
        attrs["outside_temperature"] = spec["point_position"]
    elif kind == "count":
        raw = params.get("values")
    else:
        raw = params.get(field)
    if raw is None:
        return Reading(reason="value_missing", attributes=attrs)
    texts = snapshot.get("texts", {})
    if kind == "boolean":
        if isinstance(raw, bool):
            value = raw
        elif isinstance(raw, int) and raw in (0, 1):
            value = bool(raw)
        elif isinstance(raw, str) and raw.lower() in ("true", "false", "t", "f", "on", "off"):
            value = raw.lower() in ("true", "t", "on")
        else:
            return Reading(reason="invalid_boolean", attributes=attrs)
    elif kind == "number":
        if not _number(raw):
            return Reading(reason="invalid_number", attributes=attrs)
        divisor = spec.get("divisor", 1)
        if spec["section"] != "tile" and field == "value" and "format" in params:
            divisor = 10 if params["format"] == 2 else 1
            attrs["api_format"] = params["format"]
        value = raw / divisor
        attrs["raw_value"] = raw
        attrs["divisor"] = divisor
    elif kind == "clock":
        if not _number(raw) or int(raw) != raw or not 0 <= raw < 1440:
            return Reading(reason="invalid_clock", attributes=attrs)
        value = f"{int(raw) // 60:02d}:{int(raw) % 60:02d}"
        attrs["raw_minutes"] = raw
    elif kind == "count":
        if not isinstance(raw, list):
            return Reading(reason="invalid_schedule", attributes=attrs)
        value = len(raw)
        attrs["values"] = _safe_values(raw)
        attrs["day_id"] = params.get("dayId")
    elif kind == "enum":
        text_id = raw
        if field == "value":
            option = next((p for p in params.get("options", []) if isinstance(p, dict) and p.get("value") == raw), None)
            text_id = option.get("txtId") if option is not None else None
        value = texts.get(str(text_id), f"ID {text_id}" if text_id is not None else str(raw))
        attrs["raw_value"] = raw
    elif kind == "text":
        if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
            return Reading(reason="invalid_text", attributes=attrs)
        value = str(raw)[:255]
    else:
        return Reading(reason="unsupported_transform", attributes=attrs)
    return Reading(value=value, available=True, reason="ok", attributes=attrs)

