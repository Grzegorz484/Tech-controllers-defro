"""Live menu descriptions and validated writes using the documented eModul protocol.

Wire formats: https://api-documentation.emodul.eu/tags/menu/
users_user_id_modules_module_udid_menu_menu_type_ido.yaml
No limits, access rights or available options are inferred from cached readings.
"""

from collections import Counter
from typing import Any

from .icons import icon_for
from .model import _changing, _number, _parents

KINDS = {0: "group", 1: "number", 2: "number", 3: "number", 4: "number",
         10: "switch", 11: "select", 12: "schedule_offset", 13: "schedule_onoff",
         15: "checkbox", 20: "action", 30: "curve", 35: "password"}


def _protected(item: dict) -> bool:
    params = item.get("params")
    return isinstance(params, dict) and params.get("password") in ("password", True)


def _write_parent_blocked(item: dict, elements: dict) -> bool:
    current, seen = item, set()
    while current.get("parentId") != current.get("id") and current.get("parentId") is not None:
        if current.get("id") in seen:
            return True
        seen.add(current.get("id"))
        current = elements.get(current["parentId"])
        if not isinstance(current, dict) or current.get("access") is not True or _protected(current) or _changing(current.get("duringChange")):
            return True
    return False


def _integer(value: Any) -> bool:
    return _number(value) and value == int(value)


def _range(params: dict) -> tuple[int, int, int]:
    low, high, step = params.get("min"), params.get("max"), params.get("jump", 1)
    if not all(_integer(v) for v in (low, high, step)) or low > high or step <= 0:
        raise ValueError("Brak poprawnego zakresu ustawienia w API.")
    return int(low), int(high), int(step)


def _label(item: dict, texts: dict) -> str:
    return str(texts.get(str(item.get("txtId"))) or "Ustawienie " + str(item.get("id")))


def _path(item: dict, elements: dict, texts: dict) -> str:
    labels, seen = [_label(item, texts)], {item.get("id")}
    parent = item.get("parentId")
    while parent not in seen and parent in elements:
        seen.add(parent)
        node = elements[parent]
        if parent != 0:
            labels.insert(0, _label(node, texts))
        parent = node.get("parentId")
    return " > ".join(labels)


def describe_controls(snapshot: dict | None, *, virtual: bool = False) -> list[dict]:
    """Return UI-safe menu items. Credentials and arbitrary API strings are omitted."""
    if not snapshot:
        return []
    result = []
    texts = snapshot.get("texts", {})
    for section in ("MU", "MI", "MS", "MP"):
        tree = snapshot.get("sections", {}).get(section, {})
        if tree.get("status") in ("locked", "invalid_code"):
            result.append({"key": section.lower() + "_0", "section": section, "id": 0,
                           "kind": "password", "label": "Odblokuj menu", "name": "Odblokuj menu",
                           "icon": "mdi:lock", "can_unlock": bool(snapshot.get("online")),
                           "available": False, "reason": "menu_locked"})
            continue
        if tree.get("status") != "ok":
            continue
        elements = tree.get("elements", {})
        for item in elements.values():
            if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                continue
            kind = KINDS.get(item.get("type"), "unsupported")
            if kind == "group" and _protected(item):
                kind = "password"
            blocked, missing = _parents(item, elements)
            reason = "ok"
            if not snapshot.get("online"):
                reason = "controller_offline"
            elif item.get("access") is not True or blocked or missing is not None or _write_parent_blocked(item, elements):
                reason = "access_denied"
            elif _changing(item.get("duringChange")):
                reason = "value_updating"
            elif kind in ("group", "password", "unsupported"):
                reason = kind
            label, name = _label(item, texts), _path(item, elements, texts)
            info = {"key": f"{section.lower()}_{item['id']}", "section": section,
                    "id": item["id"], "type": item.get("type"), "parent_id": item.get("parentId"),
                    "kind": kind, "label": label, "name": name,
                    "icon": icon_for(name, kind=kind), "reason": reason, "available": reason == "ok"}
            if kind == "password":
                info["can_unlock"] = reason == "password"
                result.append(info)
                continue
            params = item.get("params")
            if not isinstance(params, dict):
                info.update(available=False, reason="parameters_missing")
                result.append(info)
                continue
            try:
                if kind == "number":
                    low, high, step = _range(params)
                    value_format = params.get("format", item["type"])
                    divisor = 10 if value_format == 2 else 1
                    if not _number(params.get("value")):
                        raise ValueError("invalid_number")
                    info.update(value=params["value"] / divisor, min=low / divisor,
                                max=high / divisor, step=step / divisor, divisor=divisor,
                                unit="s" if value_format == 3 else "min" if value_format == 4 else None)
                elif kind == "switch":
                    value = params.get("value")
                    if type(value) not in (bool, int) or value not in (0, 1):
                        raise ValueError("invalid_boolean")
                    info["value"] = bool(value)
                elif kind == "select":
                    options = [o for o in params.get("options", []) if isinstance(o, dict)
                               and _integer(o.get("value")) and o.get("access") is not False]
                    labels = [str(texts.get(str(o.get("txtId"))) or o["value"]) for o in options]
                    counts = Counter(labels)
                    info["options"] = [{"value": int(o["value"]), "label": label if counts[label] == 1
                                        else f"{label} ({o['value']})"} for o, label in zip(options, labels)]
                    info["value"] = params.get("value")
                    if not options or len({o["value"] for o in options}) != len(options):
                        raise ValueError("invalid_options")
                elif kind == "checkbox":
                    options = params.get("options", [])
                    if not options or not all(_integer(o) for o in options) or not _integer(params.get("value")) or not 0 <= params["value"] < 2 ** len(options):
                        raise ValueError("invalid_options")
                    info["options"] = [{"index": n, "label": str(texts.get(str(t)) or t)}
                                       for n, t in enumerate(options)]
                    info["value"] = int(params["value"])
                elif kind == "curve":
                    low, high, _ = _range(params)
                    points = params.get("points", [])
                    if not points or not all(isinstance(p, dict) and _integer(p.get("position"))
                                             and _integer(p.get("value")) for p in points):
                        raise ValueError("invalid_points")
                    info.update(min=low, max=high, step=1,
                                points=[{"position": p["position"], "value": p["value"]} for p in points])
                elif kind == "schedule_offset":
                    low, high, _ = _range(params)
                    values = params.get("values", [])
                    if not isinstance(values, list) or len(values) not in (0, 24):
                        raise ValueError("invalid_schedule")
                    # API stores offsets from the lowest correction, not signed °C.
                    shifts = [v + low for v in values] if values else [0] * 24
                    info.update(min=low, max=high, step=1, values=shifts,
                                day=params.get("dayId"), base_id=params.get("valueObjId"))
                elif kind == "schedule_onoff":
                    slots, mask = params.get("noZones"), params.get("value")
                    if slots not in (24, 48) or not _integer(mask) or not 0 <= mask < 2 ** slots:
                        raise ValueError("invalid_schedule")
                    info.update(values=[(int(mask) >> n) & 1 for n in range(slots)], day=params.get("dayId"))
                elif kind == "action":
                    info.update(message=str(texts.get(str(params.get("txtId"))) or label),
                                action_type=params.get("type"))
                    if params.get("type") not in (0, 1, 2):
                        info.update(available=False, reason="information_only")
            except (ValueError, TypeError, KeyError):
                info.update(available=False, reason="invalid_metadata")
            result.append(info)
            if virtual and kind == "checkbox":
                for option in info.get("options", []):
                    result.append({**info, "kind": "checkbox_option", "base_key": info["key"],
                                   "mask": info["value"],
                                   "key": info["key"] + "_option_" + str(option["index"]),
                                   "index": option["index"], "name": name + " > " + option["label"],
                                   "value": bool(info["value"] & (1 << option["index"]))})
            if virtual and kind == "curve":
                for n, point in enumerate(info.get("points", [])):
                    result.append({**info, "kind": "curve_point", "base_key": info["key"], "index": n,
                                   "key": info["key"] + "_point_" + str(point["position"]),
                                   "name": name + f" > przy {point['position']} °C", "value": point["value"]})
    return result


def prepare_write(info: dict, value: Any, *, confirm: bool = False) -> tuple[dict, dict]:
    """Convert human units to one allowlisted wire payload and expected state."""
    if not info.get("available"):
        raise ValueError("Ustawienie jest niedostępne: " + info.get("reason", "missing"))
    kind = info["kind"]
    if kind == "number":
        if not _number(value):
            raise ValueError("Podaj liczbę.")
        raw = value * info["divisor"]
        low, high, step = (info[k] * info["divisor"] for k in ("min", "max", "step"))
        if abs(raw - round(raw)) > 1e-6 or not low <= raw <= high or abs((raw - low) / step - round((raw - low) / step)) > 1e-6:
            raise ValueError("Wartość jest poza zakresem albo nie odpowiada krokowi ustawienia.")
        raw = int(round(raw))
        return {"value": raw}, {"value": raw}
    if kind in ("switch", "checkbox_option"):
        if not isinstance(value, bool):
            raise ValueError("Podaj wartość włącz/wyłącz.")
        if kind == "switch":
            return {"value": int(value)}, {"value": int(value)}
        mask = sum(1 << o["index"] for o in info["options"] if
                   (value if o["index"] == info["index"] else bool(info["mask"] & (1 << o["index"]))))
        return {"many_of_many": [{"id": o["index"], "value": (mask >> o["index"]) & 1}
                                 for o in info["options"]]}, {"value": mask}
    if kind == "select":
        chosen = next((o for o in info["options"] if o["label"] == value), None)
        if chosen is None:
            raise ValueError("Wybierz jedną z dostępnych opcji.")
        return {"value": chosen["value"]}, {"value": chosen["value"]}
    if kind == "checkbox":
        if not isinstance(value, list) or len(value) != len(info["options"]) or not all(type(v) in (bool, int) and v in (0, 1) for v in value):
            raise ValueError("Nieprawidłowa lista zaznaczeń.")
        return {"many_of_many": [{"id": n, "value": int(v)} for n, v in enumerate(value)]}, {"value": sum(int(v) << n for n, v in enumerate(value))}
    if kind in ("curve", "curve_point"):
        points = [p["value"] for p in info["points"]]
        if kind == "curve_point":
            points[info["index"]] = value
        else:
            points = value
        if not isinstance(points, list) or len(points) != len(info["points"]) or not all(_integer(v) and info["min"] <= v <= info["max"] for v in points):
            raise ValueError("Nieprawidłowe punkty krzywej.")
        return {"heating_curve": [{"id": n, "value": int(v)} for n, v in enumerate(points)]}, {"points": points}
    if kind in ("schedule_offset", "schedule_onoff"):
        length = 24 if kind == "schedule_offset" else len(info["values"])
        if not isinstance(value, list) or len(value) != length or not all(_integer(v) for v in value):
            raise ValueError("Nieprawidłowa liczba przedziałów harmonogramu.")
        if kind == "schedule_offset":
            if not all(info["min"] <= v <= info["max"] for v in value):
                raise ValueError("Korekta temperatury jest poza zakresem.")
            raw = [int(v - info["min"]) for v in value]
            return {"weekly_plus_minus": {"values": raw}}, {"values": raw}
        if not all(v in (0, 1) for v in value):
            raise ValueError("Przedziały muszą być włączone albo wyłączone.")
        return {"weekly_on_off": {"values": [int(v) for v in value]}}, {"value": sum(int(v) << n for n, v in enumerate(value))}
    if kind == "action" and info.get("action_type") in (0, 1, 2):
        if confirm is not True or value is not True:
            raise ValueError("Ta czynność wymaga osobnego potwierdzenia w panelu.")
        subtype = info["action_type"]
        return {"value": {0: 2, 1: 1, 2: 3}[subtype], "type": subtype}, {}
    raise ValueError("Ten element nie jest edytowalnym ustawieniem.")
