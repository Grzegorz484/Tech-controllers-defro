"""Shared polling coordinator: one cloud fetch serves all entities."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthError, EmodulApi, RateLimitError
from .const import DOMAIN, POLL_SECONDS

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

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_snapshot(self.udid)
        except AuthError:
            raise ConfigEntryAuthFailed("Sesja eModułu wygasła. Zaloguj się ponownie.") from None
        except RateLimitError:
            raise UpdateFailed("eModuł ograniczył zapytania. Kolejna próba później.", retry_after=300) from None
        except ApiError as exc:
            raise UpdateFailed("Odczyt eModułu nie powiódł się: " + exc.reason) from None

