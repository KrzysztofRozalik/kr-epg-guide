from kr_live_epg.config import LogoConfig, StorageConfig
from kr_live_epg.logos import LogoCache
from kr_live_epg.models import CanonicalChannel
from kr_live_epg.storage import Publisher


class FakeHttp:
    def __init__(self) -> None:
        self.calls = 0

    def get_bytes(self, url: str) -> bytes:
        self.calls += 1
        assert url == "https://images.example/tvn.png"
        return b"\x89PNG\r\n\x1a\n" + b"test-image"


def test_logo_cache_publishes_stable_local_url(tmp_path) -> None:
    http = FakeHttp()
    publisher = Publisher(
        StorageConfig(
            type="local",
            local_directory=str(tmp_path),
            public_base_url="https://example.github.io/epg/v1",
        )
    )
    channel = CanonicalChannel(id="tvn.pl", name="TVN", logo="https://images.example/tvn.png")
    cache = LogoCache(
        LogoConfig(enabled=True, refresh_days=30),
        http,  # type: ignore[arg-type]
        publisher,
        profile_name="dom",
        output_directory=tmp_path / "dom",
    )

    files = cache.materialize([channel])

    assert http.calls == 1
    assert channel.logo == "https://example.github.io/epg/v1/dom/logos/tvn.png"
    assert any(path.name == "tvn.png" for path in files)
    assert any(path.name == "manifest.json" for path in files)


def test_logo_cache_reuses_fresh_file(tmp_path) -> None:
    http = FakeHttp()
    publisher = Publisher(
        StorageConfig(
            type="local",
            local_directory=str(tmp_path),
            public_base_url="https://example.github.io/epg/v1",
        )
    )
    first = CanonicalChannel(id="tvn.pl", name="TVN", logo="https://images.example/tvn.png")
    cache = LogoCache(
        LogoConfig(enabled=True),
        http,  # type: ignore[arg-type]
        publisher,
        profile_name="dom",
        output_directory=tmp_path / "dom",
    )
    cache.materialize([first])
    second = CanonicalChannel(id="tvn.pl", name="TVN", logo="https://images.example/tvn.png")

    cache.materialize([second])

    assert http.calls == 1
    assert second.logo.endswith("/dom/logos/tvn.png")
