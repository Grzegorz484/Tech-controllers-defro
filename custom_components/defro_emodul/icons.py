"""Home Assistant icons for the same heating functions shown by eModul."""

import re


def icon_for(name: str, unit: str | None = None, kind: str = "") -> str:
    text = name.casefold()
    for words, icon in (
        (("harmonogram", "tygodni", "plan pracy"), "mdi:calendar-clock"),
        (("krzywa",), "mdi:chart-bell-curve-cumulative"),
        (("cwu", "bojler", "dezynfek"), "mdi:water-boiler"),
        (("podajnik", "podawan", "podsyp"), "mdi:screw-machine-flat-top"),
        (("paliw", "zasobnik", "kalorycz"), "mdi:silo"),
        (("wentyl", "nadmuch", "obrot", "hallotron"), "mdi:fan"),
        (("pompa", "pomp", "cyrkul"), "mdi:pump"),
        (("zawór", "zawor", "otwier", "zamyk"), "mdi:valve"),
        (("podłog",), "mdi:heating-coil"),
        (("spalin",), "mdi:smoke"),
        (("ogień", "ognia", "płomie", "rozpala", "wygasza", "pid"), "mdi:fire"),
        (("grzał",), "mdi:heating-coil"),
        (("zewn", "pogod"), "mdi:thermometer-lines"),
        (("poko", "pomiesz"), "mdi:home-thermometer"),
        (("powro",), "mdi:thermometer-chevron-up"),
        (("godzin", "czas", "przerwa", "opóźn"), "mdi:timer-outline"),
        (("alarm", "termik", "zabezpiecz", "ochrona"), "mdi:shield-check"),
        (("czyszc", "ruszt"), "mdi:broom"),
        (("fabrycz",), "mdi:backup-restore"),
        (("tryb", "wybór", "rodzaj"), "mdi:tune"),
    ):
        if any(word in text for word in words):
            return icon
    if re.search(r"\bco\b", text) or "kotł" in text or "kotła" in text:
        return "mdi:radiator"
    if unit == "°C" or "temperatur" in text or "temp." in text:
        return "mdi:thermometer"
    return {"switch": "mdi:toggle-switch", "checkbox": "mdi:format-list-checks",
            "password": "mdi:lock", "action": "mdi:gesture-tap-button",
            "select": "mdi:form-select", "group": "mdi:folder-outline"}.get(kind, "mdi:tune")
