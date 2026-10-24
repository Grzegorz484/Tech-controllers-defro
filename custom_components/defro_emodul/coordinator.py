"""Shared polling coordinator: one cloud fetch serves all entities."""

from datetime import timedelta
import asyncio
import copy
import logging
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthError, EmodulApi, RateLimitError
from .const import CONF_MENU_CODES, CONF_MENU_ITEM_CODES, DOMAIN, POLL_SECONDS
from .controls import describe_controls, prepare_write

_LOGGER = logging.getLogger(__name__)


class DefroCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: EmodulApi, catalogue: dict[str, Any]) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN,
            update_interval=timedelta(seconds=POLL_SECONDS), always_update=False,
        )
        self.api = api
        self.catalogue = catalogue
        self.udid = str(entry.data["module_udid"])
        self.device_title = entry.title
        self._entry = entry
        self._io_lock = asyncio.Lock()
        self._pending = {}
        self.write_errors = {}
        self._controls_snapshot = None
        self._control_cache = {}
        self._refresh_cancel = None
        self._backoff_until = 0
        entry.async_on_unload(self._cancel_refresh)

    def _cancel_refresh(self):
        if self._refresh_cancel:
            self._refresh_cancel()
            self._refresh_cancel = None

    @property
    def controls(self):
        if self._controls_snapshot is not self.data:
            self._control_cache = {i["key"]: i for i in describe_controls(self.data, virtual=True)}
            units = {(s["section"], s["element_id"]): s.get("unit") for s in self.catalogue["entities"]}
            for info in self._control_cache.values():
                info["unit"] = info.get("unit") or units.get((info["section"], info["id"]))
            self._controls_snapshot = self.data
        return self._control_cache

    def _reconcile(self, data):
        for key, pending in list(self._pending.items()):
            item = data.get("sections", {}).get(pending["section"], {}).get("elements", {}).get(pending["id"], {})
            params = item.get("params", {})
            expected = pending["expected"]
            matches = isinstance(params, dict) and all(([p.get("value") for p in params.get("points", [])] == v if k == "points" else params.get(k) == v)
                          for k, v in expected.items())
            if item and item.get("duringChange") in ("f", False, None) and matches:
                self._pending.pop(key)
            elif monotonic() >= pending["expires"]:
                self._pending.pop(key)
                self.write_errors[key] = "Nie potwierdzono zmiany w odczycie sterownika. Sprawdź aktualną wartość."
        data = copy.deepcopy(data)
        for pending in self._pending.values():
            item = data.get("sections", {}).get(pending["section"], {}).get("elements", {}).get(pending["id"])
            if item:
                item["duringChange"] = "t"
        return data

    async def async_unlock_code(self, key, code):
        try:
            async with self._io_lock:
                if monotonic() < self._backoff_until:
                    raise ValueError("eModuł ograniczył zapytania. Spróbuj później.")
                fresh = await self.api.async_snapshot(self.udid, force_menus=True)
                info = next((i for i in describe_controls(fresh) if i["key"] == key), None)
                if not info or not info.get("can_unlock"):
                    raise ValueError("Ta pozycja nie jest dostępnym menu chronionym kodem.")
                await self.api.async_unlock_menu(self.udid, info["section"], info["id"], code)
                self.hass.config_entries.async_update_entry(self._entry, data={
                    **self._entry.data, CONF_MENU_CODES: copy.deepcopy(self.api.menu_codes),
                    CONF_MENU_ITEM_CODES: copy.deepcopy(self.api.menu_item_codes),
                })
                updated = self._reconcile(await self.api.async_snapshot(self.udid, force_menus=True))
            self.async_set_updated_data(updated)
        except AuthError:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Sesja eModułu wygasła. Zaloguj się ponownie.") from None
        except RateLimitError:
            self._backoff_until = monotonic() + 300
            raise HomeAssistantError("eModuł ograniczył zapytania. Spróbuj za 5 minut.") from None
        except ApiError as exc:
            raise HomeAssistantError("Nie udało się odblokować menu: " + exc.reason) from None
        except ValueError as exc:
            raise HomeAssistantError(str(exc)) from None

    async def async_write_control(self, key, value, *, confirm=False):
        """Recheck live permission and bounds, then send exactly one command."""
        try:
            async with self._io_lock:
                if monotonic() < self._backoff_until:
                    raise ValueError("eModuł ograniczył zapytania. Spróbuj później.")
                old = self.controls.get(key)
                if old and old.get("base_key", key) in self._pending:
                    raise ValueError("Poprzednia zmiana tego ustawienia oczekuje na potwierdzenie.")
                fresh = await self.api.async_snapshot(self.udid, force_menus=True)
                info = next((i for i in describe_controls(fresh, virtual=True) if i["key"] == key), None)
                if info is None:
                    raise ValueError("Ustawienie nie jest dostępne w bieżącym menu sterownika.")
                payload, expected = prepare_write(info, value, confirm=confirm)
                await self.api.async_set_menu(self.udid, info["section"], info["id"], payload)
                base = info.get("base_key", key)
                self.write_errors.pop(base, None)
                self._pending[base] = {"section": info["section"], "id": info["id"],
                                       "expected": expected, "expires": monotonic() + 90}
                updated = self._reconcile_pending(fresh)
            self.async_set_updated_data(updated)
            self._cancel_refresh()
            self._refresh_cancel = async_call_later(self.hass, 3, lambda _: self.hass.async_create_task(self.async_refresh()))
        except AuthError:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Sesja eModułu wygasła. Zaloguj się ponownie.") from None
        except RateLimitError:
            self._backoff_until = monotonic() + 300
            raise HomeAssistantError("eModuł ograniczył zapytania. Spróbuj za 5 minut.") from None
        except ApiError as exc:
            raise HomeAssistantError("Nie potwierdzono zapisu w eModuł: " + exc.reason + ". Sprawdź stan przed kolejną próbą.") from None
        except ValueError as exc:
            raise HomeAssistantError(str(exc)) from None

    def _reconcile_pending(self, data):
        """Mark newly accepted commands pending without confirming stale data."""
        result = copy.deepcopy(data)
        for pending in self._pending.values():
            item = result.get("sections", {}).get(pending["section"], {}).get("elements", {}).get(pending["id"])
            if item:
                item["duringChange"] = "t"
        return result

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            async with self._io_lock:
                return self._reconcile(await self.api.async_snapshot(self.udid, force_menus=bool(self._pending)))
        except AuthError:
            raise ConfigEntryAuthFailed("Sesja eModułu wygasła. Zaloguj się ponownie.") from None
        except RateLimitError:
            self._backoff_until = monotonic() + 300
            raise UpdateFailed("eModuł ograniczył zapytania. Kolejna próba później.", retry_after=300) from None
        except ApiError as exc:
            raise UpdateFailed("Odczyt eModułu nie powiódł się: " + exc.reason) from None

