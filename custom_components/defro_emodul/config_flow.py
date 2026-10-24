"""Local UI login, module selection, menu-code updates and reauthentication."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

try:
    import probatio as vol
except ImportError:  # Home Assistant versions predating the schema-library migration.
    import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import ApiError, AuthError, Authentication, EmodulApi, RateLimitError
from .const import CODE_FIELDS, CONF_MENU_CODES, CONF_MODULE_UDID, CONF_SITE, CONF_USER_ID, DOMAIN, SITES


def _password_selector():
    return selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))


def _login_schema(site: str | None = None):
    fields = {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): _password_selector(),
    }
    if site is not None:
        fields = {vol.Required(CONF_SITE, default=site): vol.In(SITES), **fields}
    return vol.Schema(fields)


def _code_fields(current: dict[str, str] | None = None):
    current = current or {}
    return {
        vol.Optional(field, default=current.get(menu, "")): _password_selector()
        for menu, field in CODE_FIELDS.items()
    }


def _codes_from(data: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    codes, errors = {}, {}
    for menu, name in CODE_FIELDS.items():
        code = str(data.get(name, "")).strip()
        if code and not re.fullmatch(r"[0-9]{1,16}", code):
            errors[name] = "invalid_code_format"
        elif code:
            codes[menu] = code
    return codes, errors


def _supported(module: dict[str, Any]) -> bool:
    return module.get("type") == "pellet" and (
        str(module.get("company", "")).lower() == "defro"
        or bool(re.search(r"ST[- ]?9730", str(module.get("version", "")), re.I))
    )


def _supported_snapshot(snapshot: dict[str, Any]) -> bool:
    item = snapshot.get("sections", {}).get("tile", {}).get("elements", {}).get(2000, {})
    params = item.get("params") or {}
    name = params.get("controllerName") if isinstance(params, dict) else None
    # Prefer the actual model tile over a possibly generic module-list label.
    version = str(name or snapshot.get("metadata", {}).get("version", ""))
    return bool(re.search(r"\bST[- ]?9730\b", version, re.I))


def _error_key(exc: ApiError) -> str:
    if isinstance(exc, AuthError):
        return "invalid_auth"
    if isinstance(exc, RateLimitError):
        return "rate_limit"
    return "cannot_connect"


class DefroConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._api: EmodulApi | None = None
        self._modules: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = {}
        site = "emodul.pl"
        if user_input is not None:
            site = user_input[CONF_SITE]
            api = EmodulApi(async_get_clientsession(self.hass), site)
            try:
                await api.async_authenticate(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
                self._modules = [m for m in await api.async_modules() if _supported(m)]
            except ApiError as exc:
                errors["base"] = _error_key(exc)
            else:
                if not self._modules:
                    return self.async_abort(reason="no_supported_module")
                self._api = api
                return await self.async_step_module()
        return self.async_show_form(step_id="user", data_schema=_login_schema(site), errors=errors)

    async def async_step_module(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._api is None or self._api.authentication is None:
            return self.async_abort(reason="session_missing")
        errors = {}
        if user_input is not None:
            udid = user_input[CONF_MODULE_UDID]
            selected = next((m for m in self._modules if str(m["udid"]) == udid), None)
            if selected is None:
                errors["base"] = "module_missing"
            else:
                await self.async_set_unique_id(udid)
                self._abort_if_unique_id_configured()
                codes, errors = _codes_from(user_input)
                if not errors:
                    self._api.menu_codes = codes
                    try:
                        snapshot = await self._api.async_snapshot(udid, force_menus=True)
                    except ApiError as exc:
                        errors["base"] = _error_key(exc)
                    else:
                        if snapshot.get("online") and not _supported_snapshot(snapshot):
                            errors["base"] = "unsupported_model"
                        for menu, code_field in CODE_FIELDS.items():
                            if codes.get(menu) and snapshot.get("sections", {}).get(menu, {}).get("status") == "invalid_code":
                                errors[code_field] = "invalid_code"
                        if not errors:
                            auth = self._api.authentication
                            return self.async_create_entry(
                                title=str(selected.get("name") or "DEFRO APC Slim"),
                                data={
                                    CONF_SITE: self._api.site, CONF_USER_ID: auth.user_id,
                                    CONF_TOKEN: auth.token, CONF_MODULE_UDID: udid,
                                    CONF_MENU_CODES: codes,
                                },
                            )
        choices = {
            str(m["udid"]): str(m.get("name") or "DEFRO") + " — " + str(m.get("version", ""))
            for m in self._modules
        }
        schema = vol.Schema({
            vol.Required(CONF_MODULE_UDID, default=next(iter(choices))): vol.In(choices),
            **_code_fields(),
        })
        return self.async_show_form(step_id="module", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            api = EmodulApi(async_get_clientsession(self.hass), entry.data[CONF_SITE])
            try:
                auth = await api.async_authenticate(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
                modules = await api.async_modules()
            except ApiError as exc:
                errors["base"] = _error_key(exc)
            else:
                udid = str(entry.data[CONF_MODULE_UDID])
                if not any(str(m.get("udid")) == udid for m in modules):
                    errors["base"] = "wrong_account"
                else:
                    await self.async_set_unique_id(udid)
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: auth.token, CONF_USER_ID: auth.user_id})
        return self.async_show_form(step_id="reauth_confirm", data_schema=_login_schema(), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors = {}
        current = dict(entry.data.get(CONF_MENU_CODES, {}))
        if user_input is not None:
            codes, errors = _codes_from(user_input)
            if not errors:
                api = EmodulApi(
                    async_get_clientsession(self.hass), entry.data[CONF_SITE],
                    Authentication(str(entry.data[CONF_USER_ID]), entry.data[CONF_TOKEN]),
                    menu_codes=codes,
                )
                try:
                    # A supplied menu code is tried once; there is no guessing.
                    for menu, field in CODE_FIELDS.items():
                        if codes.get(menu) and (await api.async_menu(str(entry.data[CONF_MODULE_UDID]), menu)).get("status") == "invalid_code":
                            errors[field] = "invalid_code"
                except ApiError as exc:
                    errors["base"] = _error_key(exc)
                if not errors:
                    await self.async_set_unique_id(str(entry.data[CONF_MODULE_UDID]))
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(entry, data_updates={CONF_MENU_CODES: codes})
        return self.async_show_form(step_id="reconfigure", data_schema=vol.Schema(_code_fields(current)), errors=errors)

