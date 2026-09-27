from __future__ import annotations

import html
from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..config import PlaylistConfig
from ..exceptions import SourceError
from ..http import HttpClient
from ..models import Channel


def _portal_root(value: str) -> str:
    parts = urlsplit(value.strip())
    path = parts.path.rstrip("/")
    if path.endswith("/c"):
        path = path[:-2]
    for ending in ("/portal.php", "/server/load.php"):
        if path.endswith(ending):
            path = path[: -len(ending)]
    return urlunsplit((parts.scheme, parts.netloc, path.rstrip("/"), "", ""))


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "js" in payload:
        return payload["js"]
    return payload


class StalkerProvider:
    """Catalogue-only MAG/Stalker client for portals the user is authorised to use."""

    def __init__(self, config: PlaylistConfig, http: HttpClient) -> None:
        self.config = config
        self.http = http

    def _request(
        self,
        endpoint: str,
        params: dict[str, str],
        *,
        token: str | None = None,
    ) -> Any:
        if not self.config.mac:
            raise SourceError("Brak adresu MAC dla Stalker")
        mac = self.config.mac.get_secret_value()
        headers = {
            "User-Agent": self.config.stalker_user_agent,
            "X-User-Agent": "Model: MAG254; Link: Ethernet",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{_portal_root(self.config.portal_url or '')}/c/",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        query = {**params, "JsHttpRequest": "1-xml"}
        return self.http.get_json(endpoint, params=query, headers=headers, cookies={"mac": mac})

    def _endpoint_and_token(self) -> tuple[str, str]:
        if not self.config.portal_url:
            raise SourceError("Brak URL portalu Stalker")
        root = _portal_root(self.config.portal_url)
        errors: list[str] = []
        for endpoint in (f"{root}/portal.php", f"{root}/server/load.php"):
            try:
                payload = _unwrap(
                    self._request(
                        endpoint,
                        {"type": "stb", "action": "handshake", "token": ""},
                    )
                )
                token = payload.get("token") if isinstance(payload, dict) else None
                if token:
                    return endpoint, str(token)
            except Exception as exc:  # try the two well-known portal layouts
                errors.append(type(exc).__name__)
        raise SourceError(
            "Portal Stalker odrzucił handshake (sprawdzono portal.php i server/load.php): "
            + ", ".join(errors)
        )

    def _activate_profile(self, endpoint: str, token: str) -> None:
        params = {"type": "stb", "action": "get_profile", "hd": "1"}
        if self.config.serial:
            params["sn"] = self.config.serial.get_secret_value()
        if self.config.device_id:
            device = self.config.device_id.get_secret_value()
            params["device_id"] = device
            params["device_id2"] = device
        with suppress(Exception):
            self._request(endpoint, params, token=token)
        # Some portals do not require get_profile and reject unknown MAG fields.

    def fetch_channels(self) -> list[Channel]:
        endpoint, token = self._endpoint_and_token()
        self._activate_profile(endpoint, token)
        payload = _unwrap(
            self._request(
                endpoint,
                {"type": "itv", "action": "get_all_channels", "force_ch_link_check": ""},
                token=token,
            )
        )
        if isinstance(payload, dict):
            payload = payload.get("data") or payload.get("channels") or []
        if not isinstance(payload, list):
            raise SourceError("Portal Stalker nie zwrócił listy kanałów")

        channels: list[Channel] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            provider_id = str(item.get("id") or item.get("ch_id") or "").strip()
            name = html.unescape(str(item.get("name") or "")).strip()
            if not provider_id or not name:
                continue
            epg_id = str(
                item.get("xmltv_id") or item.get("epg_channel_id") or item.get("epg_id") or ""
            ).strip()
            channels.append(
                Channel(
                    source_id=self.config.source_id,
                    provider_id=provider_id,
                    name=name,
                    tvg_id=epg_id or None,
                    group=str(item.get("tv_genre_id") or item.get("category_id") or "") or None,
                    logo=str(item.get("logo") or "").strip() or None,
                    aliases=[epg_id] if epg_id else [],
                    attributes={"number": str(item.get("number") or "")},
                )
            )
        return channels
