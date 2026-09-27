from pydantic import SecretStr

from kr_live_epg.config import PlaylistConfig
from kr_live_epg.models import PlaylistKind
from kr_live_epg.providers.stalker import StalkerProvider, _portal_root
from kr_live_epg.providers.xtream import XtreamProvider


class FakeXtreamHttp:
    def get_json(self, url, *, params=None, **kwargs):
        if params["action"] == "get_live_categories":
            return [{"category_id": "10", "category_name": "Sport"}]
        return [
            {
                "stream_id": 123,
                "name": "[PL] Polsat Sport 1 FHD",
                "epg_channel_id": "ps1",
                "category_id": "10",
                "stream_icon": "https://img.example/ps1.png",
            }
        ]


def test_xtream_catalogue_builds_protected_stream_url() -> None:
    config = PlaylistConfig(
        type=PlaylistKind.XTREAM,
        base_url="https://xtream.example",
        username=SecretStr("user@example"),
        password=SecretStr("p/a ss"),
    )
    channels = XtreamProvider(config, FakeXtreamHttp()).fetch_channels()  # type: ignore[arg-type]
    assert len(channels) == 1
    assert channels[0].tvg_id == "ps1"
    assert channels[0].group == "Sport"
    assert channels[0].stream_url == "https://xtream.example/live/user%40example/p%2Fa%20ss/123.ts"


class FakeStalkerHttp:
    def get_json(self, url, *, params=None, **kwargs):
        action = params["action"]
        if action == "handshake":
            return {"js": {"token": "secret-session-token"}}
        if action == "get_profile":
            return {"js": {"id": 1}}
        if action == "get_all_channels":
            return {
                "js": {
                    "data": [
                        {
                            "id": "77",
                            "name": "[PL] Polsat Sport 1 HD",
                            "xmltv_id": "ps1",
                            "logo": "https://img.example/ps1.png",
                            "tv_genre_id": "4",
                        }
                    ]
                }
            }
        raise AssertionError(action)


def test_stalker_handshake_and_catalogue() -> None:
    config = PlaylistConfig(
        type=PlaylistKind.STALKER,
        portal_url="https://portal.example/stalker_portal/c/",
        mac=SecretStr("00:1A:79:00:00:01"),
    )
    channels = StalkerProvider(config, FakeStalkerHttp()).fetch_channels()  # type: ignore[arg-type]
    assert _portal_root(config.portal_url or "") == "https://portal.example/stalker_portal"
    assert len(channels) == 1
    assert channels[0].provider_id == "77"
    assert channels[0].tvg_id == "ps1"
    assert channels[0].stream_url is None
