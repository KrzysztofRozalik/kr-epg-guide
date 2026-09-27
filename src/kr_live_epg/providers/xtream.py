from __future__ import annotations

from urllib.parse import quote

from ..config import PlaylistConfig
from ..exceptions import SourceError
from ..http import HttpClient
from ..models import Channel


class XtreamProvider:
    """Read a user's lawful Xtream catalogue without logging credentials."""

    def __init__(self, config: PlaylistConfig, http: HttpClient) -> None:
        self.config = config
        self.http = http

    def fetch_channels(self) -> list[Channel]:
        if not self.config.base_url or not self.config.username or not self.config.password:
            raise SourceError("Niepełna konfiguracja Xtream")
        base = self.config.base_url.rstrip("/")
        username = self.config.username.get_secret_value()
        password = self.config.password.get_secret_value()
        common = {"username": username, "password": password}

        category_names: dict[str, str] = {}
        try:
            categories = self.http.get_json(
                f"{base}/player_api.php", params={**common, "action": "get_live_categories"}
            )
            if isinstance(categories, list):
                category_names = {
                    str(item.get("category_id")): str(item.get("category_name") or "")
                    for item in categories
                    if isinstance(item, dict)
                }
        except SourceError:
            # Category names are optional; the channel catalogue is not.
            pass

        payload = self.http.get_json(
            f"{base}/player_api.php", params={**common, "action": "get_live_streams"}
        )
        if not isinstance(payload, list):
            raise SourceError("Serwer Xtream nie zwrócił katalogu kanałów live")
        extension = "m3u8" if self.config.output == "m3u8" else "ts"
        channels: list[Channel] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            stream_id = str(item.get("stream_id") or "").strip()
            if not name or not stream_id:
                continue
            epg_id = str(item.get("epg_channel_id") or "").strip() or None
            stream_url = (
                f"{base}/live/{quote(username, safe='')}/{quote(password, safe='')}/"
                f"{quote(stream_id, safe='')}.{extension}"
            )
            category_id = str(item.get("category_id") or "")
            channels.append(
                Channel(
                    source_id=self.config.source_id,
                    provider_id=stream_id,
                    name=name,
                    tvg_id=epg_id,
                    group=category_names.get(category_id) or None,
                    logo=str(item.get("stream_icon") or "").strip() or None,
                    stream_url=stream_url,
                    aliases=[epg_id] if epg_id else [],
                    attributes={
                        "category-id": category_id,
                        "tv-archive": str(item.get("tv_archive") or "0"),
                    },
                )
            )
        return channels
