from datetime import UTC, datetime, timedelta

from kr_live_epg.config import (
    AppConfig,
    GuideSourceConfig,
    PlaylistConfig,
    ProfileConfig,
    SentinelConfig,
    StorageConfig,
)
from kr_live_epg.models import PlaylistKind
from kr_live_epg.pipeline import EpgPipeline
from kr_live_epg.providers.xmltv import parse_xmltv


def test_end_to_end_build_normalizes_playlist_and_emits_xmltv(tmp_path) -> None:
    start = datetime.now(UTC) + timedelta(hours=1)
    stop = start + timedelta(hours=2)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <tv><channel id="ps1"><display-name>Polsat Sport 1</display-name></channel>
    <programme start="{start.strftime("%Y%m%d%H%M%S %z")}"
      stop="{stop.strftime("%Y%m%d%H%M%S %z")}" channel="ps1">
      <title>Magazyn sportowy</title><desc>Pełny opis programu.</desc>
      <category>Sport</category>
    </programme></tv>"""
    guide_path = tmp_path / "guide.xml"
    guide_path.write_text(xml, encoding="utf-8")
    playlist_path = tmp_path / "input.m3u"
    playlist_path.write_text(
        '#EXTM3U\n#EXTINF:-1 tvg-id="ps1",[PL] Polsat Sport 1 FHD 50FPS\n'
        "https://stream.example/live\n",
        encoding="utf-8",
from datetime import UTC, datetime, timedelta

from kr_live_epg.config import (
    AppConfig,
    GuideSourceConfig,
    PlaylistConfig,
    ProfileConfig,
    SentinelConfig,
    StorageConfig,
)
from kr_live_epg.models import PlaylistKind
from kr_live_epg.pipeline import EpgPipeline
from kr_live_epg.providers.xmltv import parse_xmltv


def test_end_to_end_build_normalizes_playlist_and_emits_xmltv(tmp_path) -> None:
    start = datetime.now(UTC) + timedelta(hours=1)
    stop = start + timedelta(hours=2)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <tv><channel id="ps1"><display-name>Polsat Sport 1</display-name>
      <display-name>Polsat Sport 1 FHD PL</display-name></channel>
    <programme start="{start.strftime("%Y%m%d%H%M%S %z")}"
      stop="{stop.strftime("%Y%m%d%H%M%S %z")}" channel="ps1">
      <title>Magazyn sportowy</title><desc>Pełny opis programu.</desc>
      <category>Sport</category>
    </programme></tv>"""
    guide_path = tmp_path / "guide.xml"
    guide_path.write_text(xml, encoding="utf-8")
    playlist_path = tmp_path / "input.m3u"
    playlist_path.write_text(
        '#EXTM3U\n#EXTINF:-1 tvg-id="ps1",[PL] Polsat Sport 1 FHD 50FPS\n'
        "https://stream.example/live\n",
        encoding="utf-8",
    )
    config = AppConfig(
        state_path=str(tmp_path / "state.sqlite3"),
        guide_sources=[GuideSourceConfig(id="fixture", url=str(guide_path))],
        profiles={
            "dom": ProfileConfig(
                playlist=PlaylistConfig(
                    type=PlaylistKind.M3U,
                    path=str(playlist_path),
                    source_id="box",
                ),
                emit_uncompressed_xml=False,
            )
        },
        sentinel=SentinelConfig(enabled=False),
        storage=StorageConfig(type="local", local_directory=str(tmp_path / "output")),
    )
    stats = EpgPipeline(config).run()
    assert stats[0].matched_channel_count == 1
    assert stats[0].programme_count == 1
    assert stats[0].channels_with_real_epg >= 1
    assert (tmp_path / "output/dom/coverage.json").is_file()
    assert not (tmp_path / "output/dom/epg.xml").exists()
    normalized = (tmp_path / "output/dom/playlist.m3u").read_text(encoding="utf-8")
    assert 'tvg-id="polsat-sport-1.pl"' in normalized
    assert ",[PL]" not in normalized
    output_guide = parse_xmltv(
        (tmp_path / "output/dom/epg.xml.gz").read_bytes(), source_id="result"
    )
    canonical = [item for item in output_guide.programmes if item.channel_id == "polsat-sport-1.pl"]
    assert len(canonical) == 1
    assert canonical[0].description == "Pełny opis programu. Gatunek: Sport."
    output_channel = next(
        item for item in output_guide.channels if item.provider_id == "polsat-sport-1.pl"
    )
    assert "Polsat Sport 1 FHD PL" in output_channel.aliases
    )
    config = AppConfig(
        state_path=str(tmp_path / "state.sqlite3"),
        guide_sources=[GuideSourceConfig(id="fixture", url=str(guide_path))],
        profiles={
            "dom": ProfileConfig(
                playlist=PlaylistConfig(
                    type=PlaylistKind.M3U,
                    path=str(playlist_path),
                    source_id="box",
                ),
                emit_uncompressed_xml=False,
            )
        },
        sentinel=SentinelConfig(enabled=False),
        storage=StorageConfig(type="local", local_directory=str(tmp_path / "output")),
    )
    stats = EpgPipeline(config).run()
    assert stats[0].matched_channel_count == 1
    assert stats[0].programme_count == 1
    assert stats[0].channels_with_real_epg >= 1
    assert (tmp_path / "output/dom/coverage.json").is_file()
    assert not (tmp_path / "output/dom/epg.xml").exists()
    normalized = (tmp_path / "output/dom/playlist.m3u").read_text(encoding="utf-8")
    assert 'tvg-id="polsat-sport-1.pl"' in normalized
    assert ",[PL]" not in normalized
    output_guide = parse_xmltv(
        (tmp_path / "output/dom/epg.xml.gz").read_bytes(), source_id="result"
    )
    canonical = [item for item in output_guide.programmes if item.channel_id == "polsat-sport-1.pl"]
    assert len(canonical) == 1
    assert canonical[0].description == "Pełny opis programu. Gatunek: Sport."
