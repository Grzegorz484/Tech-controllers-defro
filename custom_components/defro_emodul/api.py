"""Small eModuł client with explicit menu-write endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from time import monotonic
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import MENU_POLL_SECONDS, MENU_TYPES, SITES, TRANSLATION_POLL_SECONDS, VERSION


class ApiError(Exception):
    """An API error whose text never includes credentials, URLs or bodies."""

    def __init__(self, reason: str, status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


class AuthError(ApiError):
    """An expired or invalid account session."""


class RateLimitError(ApiError):
    """Cloud throttling; stop the current polling cycle."""


@dataclass(frozen=True)
class Authentication:
    user_id: str = field(repr=False)
    token: str = field(repr=False)


def _segment(value: Any) -> str:
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value):
        raise ApiError("invalid_identifier")
    return quote(value, safe="")


def elements_from(payload: Any) -> list[dict[str, Any]] | None:
    # GET /modules/{udid} embeds tiles as a list; /tiles wraps it in elements.
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return None
    data = payload.get("data", payload)
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        return None
    return [item for item in data["elements"] if isinstance(item, dict)]


def _index(elements: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {item["id"]: item for item in elements if isinstance(item.get("id"), int)}


def _locked(elements: list[dict[str, Any]]) -> bool:
    return any(
        item.get("id") == 0
        and isinstance(item.get("params"), dict)
        and item["params"].get("password") in ("password", True)
        for item in elements
    )


def metadata_from(module: dict[str, Any]) -> dict[str, Any]:
    return {
        key: module[key]
        for key in ("type", "version", "company", "controllerStatus", "moduleStatus")
        if key in module
    }


def is_online(metadata: dict[str, Any]) -> bool:
    """Cached cloud values must not be presented as live when disconnected."""
    for key in ("controllerStatus", "moduleStatus"):
        status = metadata.get(key)
        if status is None:
            continue
        if str(status).lower() not in ("active", "online", "connected", "true", "1"):
            return False
    return True


class EmodulApi:
    """Use the Home Assistant-owned session; never close that session."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        site: str,
        authentication: Authentication | None = None,
        menu_codes: dict[str, str] | None = None,
        fallback_texts: dict[str, str] | None = None,
        menu_item_codes: dict[str, dict[str, str]] | None = None,
    ) -> None:
        if site not in SITES:
            raise ApiError("invalid_site")
        self.session = session
        self.site = site
        self.authentication = authentication
        self.menu_codes = dict(menu_codes or {})
        self.menu_item_codes = {s: dict(codes) for s, codes in (menu_item_codes or {}).items()}
        self._texts = dict(fallback_texts or {})
        self._last_translation_attempt = -float("inf")
        self._menu_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        write_path = re.fullmatch(r"/users/[0-9]+/modules/[A-Za-z0-9_-]+/menu/(MU|MI|MS|MP)/ido/[0-9]+", path)
        if method != "GET" and not (method == "POST" and (path == "/authentication" or write_path)):
            raise ApiError("write_blocked")
        if not path.startswith("/") or "://" in path or ".." in path:
            raise ApiError("invalid_path")
        headers = {"Accept": "application/json", "User-Agent": "defro-emodul/" + VERSION}
        if self.authentication and path != "/authentication":
            headers["Authorization"] = "Bearer " + self.authentication.token
        try:
            async with self.session.request(
                method,
                "https://" + self.site + "/api/v1" + path,
                json=body,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as response:
                status = response.status
                if status == 401:
                    raise AuthError("invalid_auth", status)
                if status == 429:
                    raise RateLimitError("rate_limit", status)
                if status != 200:
                    raise ApiError("http_error", status)
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > 16 * 1024 * 1024:
                        raise ApiError("response_too_large")
                    chunks.append(chunk)
                return json.loads(b"".join(chunks))
        except (aiohttp.ClientError, TimeoutError, UnicodeError, json.JSONDecodeError):
            # aiohttp exceptions may include a code in a URL. Discard their text.
            raise ApiError("cannot_connect") from None

    async def async_authenticate(self, username: str, password: str) -> Authentication:
        result = await self._request("POST", "/authentication", {
            "username": username,
            "password": password,
            "rememberMe": False,
            "languageId": 18,
            "remote": False,
        })
        if not isinstance(result, dict) or result.get("authenticated") is not True:
            raise AuthError("invalid_auth")
        token, user_id = result.get("token"), result.get("user_id")
        if not isinstance(token, str) or not token or isinstance(user_id, bool):
            raise AuthError("invalid_auth")
        try:
            identifier = str(int(user_id))
        except (ValueError, TypeError):
            raise AuthError("invalid_auth") from None
        self.authentication = Authentication(identifier, token)
        return self.authentication

    async def async_set_menu(self, udid: str, section: str, element_id: int, payload: dict[str, Any]) -> None:
        """Send one validated menu change, without automatic POST retries."""
        if section not in MENU_TYPES or type(element_id) is not int or element_id < 0:
            raise ApiError("write_blocked")
        if len(payload) != 1 and set(payload) != {"value", "type"}:
            raise ApiError("write_blocked")
        if not set(payload) <= {"value", "type", "weekly_plus_minus", "weekly_on_off", "many_of_many", "heating_curve"}:
            raise ApiError("write_blocked")
        data = dict(payload)
        if code := self._write_pin(section, element_id):
            data["pin"] = code
        path = self._user_prefix() + "/modules/" + _segment(udid) + "/menu/" + section + "/ido/" + str(element_id)
        result = await self._request("POST", path, data)
        if not isinstance(result, dict) or result.get("status") != "success" or result.get("data") not in ("1", 1) or result.get("error"):
            raise ApiError("write_rejected")
        self._menu_cache.pop(section, None)

    def _write_pin(self, section: str, element_id: int) -> str | None:
        elements = self._menu_cache.get(section, (0, {}))[1].get("elements", {})
        current, seen = elements.get(element_id), set()
        while isinstance(current, dict) and current.get("id") not in seen:
            seen.add(current.get("id"))
            if code := self.menu_item_codes.get(section, {}).get(str(current.get("id"))):
                return code
            parent = current.get("parentId")
            if parent == current.get("id"):
                break
            current = elements.get(parent)
        return self.menu_codes.get(section)

    async def async_unlock_menu(self, udid: str, section: str, element_id: int, code: str) -> None:
        """Try one explicitly supplied code; restore previous access on rejection."""
        if section not in MENU_TYPES or type(element_id) is not int or element_id < 0 or not isinstance(code, str) or not re.fullmatch(r"[0-9]{1,16}", code):
            raise ApiError("invalid_code")
        root_before = dict(self.menu_codes)
        items_before = {s: dict(c) for s, c in self.menu_item_codes.items()}
        if element_id == 0:
            self.menu_codes[section] = code
        else:
            self.menu_item_codes.setdefault(section, {})[str(element_id)] = code
        try:
            result = await self.async_menu(udid, section)
            node = result.get("elements", {}).get(element_id, {})
            params = node.get("params", {})
            if result["status"] == "error":
                raise ApiError("cannot_connect")
            if result["status"] != "ok" or (element_id != 0 and (not isinstance(params, dict) or params.get("password") in ("password", True) or not node)):
                raise ApiError("invalid_code")
        except ApiError:
            self.menu_codes, self.menu_item_codes = root_before, items_before
            raise
        self._menu_cache.pop(section, None)

    def _user_prefix(self) -> str:
        if self.authentication is None:
            raise AuthError("invalid_auth")
        return "/users/" + _segment(self.authentication.user_id)

    async def async_modules(self) -> list[dict[str, Any]]:
        result = await self._request("GET", self._user_prefix() + "/modules")
        if not isinstance(result, list):
            raise ApiError("invalid_response")
        allowed = ("udid", "name", "type", "company", "version", "controllerStatus", "moduleStatus")
        return [
            {key: item[key] for key in allowed if key in item}
            for item in result
            if isinstance(item, dict) and item.get("udid")
        ]

    async def async_menu(self, udid: str, menu_type: str) -> dict[str, Any]:
        if menu_type not in MENU_TYPES:
            raise ApiError("invalid_menu")
        path = self._user_prefix() + "/modules/" + _segment(udid) + "/menu/" + menu_type + "/"
        try:
            result = await self._request("GET", path)
            elements = elements_from(result)
            if elements is None:
                return {"status": "no_elements", "elements": {}}
            codes = dict(self.menu_item_codes.get(menu_type, {}))
            if root_code := self.menu_codes.get(menu_type):
                codes["0"] = root_code
            if _locked(elements) or codes:
                if not codes:
                    return {"status": "locked", "elements": {}}
                if any(not re.fullmatch(r"[0-9]{1,16}", str(c)) or not str(i).isdecimal() for i, c in codes.items()):
                    return {"status": "invalid_code", "elements": {}}
                pins = ",".join(str(i) + ":" + str(c) for i, c in sorted(codes.items(), key=lambda pair: int(pair[0])))
                result = await self._request("GET", path + pins)
                elements = elements_from(result)
                if elements is None or _locked(elements):
                    return {"status": "invalid_code", "elements": {}}
            return {"status": "ok", "elements": _index(elements)}
        except (AuthError, RateLimitError):
            raise
        except ApiError as exc:
            if exc.status == 422:
                return {"status": "invalid_code", "elements": {}}
            return {"status": "error", "http_status": exc.status, "elements": {}}

    async def async_snapshot(self, udid: str, *, force_menus: bool = False) -> dict[str, Any]:
        # The separate status query prevents cached readings appearing live offline.
        modules = await self.async_modules()
        module = next((item for item in modules if str(item.get("udid")) == udid), None)
        if module is None:
            raise ApiError("module_missing")
        metadata = metadata_from(module)
        online = is_online(metadata)
        if not online:
            return {"metadata": metadata, "online": False, "sections": {}, "texts": self._texts}
        base = self._user_prefix() + "/modules/" + _segment(udid)
        payload = await self._request("GET", base)
        if not isinstance(payload, dict):
            raise ApiError("invalid_response")
        elements = elements_from(payload.get("tiles"))
        if elements is None:
            raise ApiError("invalid_response")
        sections = {"tile": {"status": "ok", "elements": _index(elements)}}
        for menu_type in MENU_TYPES:
            now = monotonic()
            cached = self._menu_cache.get(menu_type)
            retry = cached is not None and cached[1].get("status") == "error"
            if force_menus or cached is None or retry or now - cached[0] >= MENU_POLL_SECONDS:
                result = await self.async_menu(udid, menu_type)
                self._menu_cache[menu_type] = (monotonic(), result)
            sections[menu_type] = self._menu_cache[menu_type][1]
        now = monotonic()
        if now - self._last_translation_attempt >= TRANSLATION_POLL_SECONDS:
            self._last_translation_attempt = now
            try:
                pack = await self._request("GET", "/i18n/pl")
                data = pack.get("data") if isinstance(pack, dict) else None
                if isinstance(data, dict):
                    self._texts = {**self._texts, **{str(k): v for k, v in data.items() if isinstance(v, str)}}
            except (AuthError, RateLimitError):
                raise
            except ApiError:
                # Stable labels from the catalogue still work without this pack.
                pass
        return {"metadata": metadata, "online": True, "sections": sections, "texts": self._texts}

