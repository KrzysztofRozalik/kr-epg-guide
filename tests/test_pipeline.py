from datetime import UTC, datetime, timedelta

import pytest

from kr_live_epg.config import (
    AppConfig,
    GuideSourceConfig,
    PlaylistConfig,
    ProfileConfig,
    SentinelConfig,
    StorageConfig,
)
from kr_live_epg.models import Channel, Guide, PlaylistKind, Programme
from kr_live_epg.pipeline import EpgPipeline
from kr_live_epg.providers.xmltv import parse_xmltv
from kr_live_epg.registry import ChannelRegistry


@pytest.mark.parametrize(
    ("base_name", "variant_name"),
    [
        ("Sky Sports F1", "Sky Sports F1 UHD"),
        ("Travel XP", "Travelxp 4K"),
        ("Separate Feed", "Separate Feed HD"),
    ],
)
def test_distinct_source_quality_feeds_stay_separate(base_name, variant_name) -> None:
    start = datetime.now(UTC)
    registry = ChannelRegistry([])
    for source_id in ("first", "second"):
        guide = Guide(
            source_id=source_id,
            channels=[
                Channel(source_id=source_id, provider_id="base", name=base_name),
                Channel(source_id=source_id, provider_id="variant", name=variant_name),
            ],
            programmes=[
                Programme(
                    channel_id=provider_id,
                    start=start,
                    stop=start + timedelta(hours=1),
                    title=provider_id,
                    source_id=source_id,
                )
                for provider_id in ("base", "variant")
            ],
        )
        mapped = {
            item.title: item.channel_id
            for item in EpgPipeline._canonicalize_guides([guide], registry)
        }
        assert mapped["base"] != mapped["variant"]
        assert registry.get(mapped["base"]).name == base_name
        assert registry.get(mapped["variant"]).name == variant_name
    assert len(registry.channels) == 2


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


def test_guide_does_not_collapse_legacy_and_current_channel_names() -> None:
    start = datetime.now(UTC)
    guide = Guide(
        source_id="fixture",
        channels=[
            Channel(source_id="fixture", provider_id="old", name="Polsat Sport"),
            Channel(source_id="fixture", provider_id="new", name="Polsat Sport 1"),
        ],
        programmes=[
            Programme(
                channel_id="old",
                start=start,
                stop=start + timedelta(hours=1),
                title="Stara ramówka",
                source_id="fixture",
            ),
            Programme(
                channel_id="new",
                start=start,
                stop=start + timedelta(hours=1),
                title="Aktualna ramówka",
                source_id="fixture",
            ),
        ],
    )
    registry = ChannelRegistry.load()
    programmes = EpgPipeline._canonicalize_guides([guide], registry)
    mapped = {item.title: item.channel_id for item in programmes}
    assert mapped["Aktualna ramówka"] == "polsat-sport-1.pl"
    assert mapped["Stara ramówka"] != "polsat-sport-1.pl"


def test_source_aliases_do_not_pollute_canonical_registry() -> None:
    guide = Guide(
        source_id="fixture",
        channels=[
            Channel(
                source_id="fixture",
                provider_id="tvn",
                name="TVN",
                aliases=["NIEPOWIĄZANY KANAŁ"],
            )
        ],
    )
    registry = ChannelRegistry.load()
    EpgPipeline._canonicalize_guides([guide], registry)
    assert "NIEPOWIĄZANY KANAŁ" not in registry.get("tvn.pl").aliases


def test_dedicated_4k_and_foreign_canal_plus_schedules_stay_separate() -> None:
    start = datetime.now(UTC)
    guide = Guide(
        source_id="fixture",
        channels=[
            Channel(source_id="fixture", provider_id="pl4k", name="Canal+ 4K Ultra HD"),
            Channel(source_id="fixture", provider_id="fr", name="Canal+"),
        ],
        programmes=[
            Programme(
                channel_id="pl4k",
                start=start,
                stop=start + timedelta(hours=1),
                title="Polska ramówka 4K",
                source_id="fixture",
            ),
            Programme(
                channel_id="fr",
                start=start,
                stop=start + timedelta(hours=1),
                title="Francuska ramówka",
                source_id="fixture",
            ),
        ],
    )
    registry = ChannelRegistry.load()
    mapped = {
        entry.title: entry.channel_id
        for entry in EpgPipeline._canonicalize_guides([guide], registry)
    }
    assert mapped["Polska ramówka 4K"] == "canal-plus-4k.pl"
    assert mapped["Francuska ramówka"] == "canal-plus.pl"


def test_guide_identity_ignores_unrelated_aliases_and_provider_ids() -> None:
    start = datetime.now(UTC)
    guide = Guide(
        source_id="fixture",
        channels=[
            Channel(
                source_id="fixture",
                provider_id="tvn.pl",
                name="Niepowiązana Stacja",
                aliases=["TVN"],
            )
        ],
        programmes=[
            Programme(
                channel_id="tvn.pl",
                start=start,
                stop=start + timedelta(hours=1),
                title="Obca ramówka",
                source_id="fixture",
            )
        ],
    )
    registry = ChannelRegistry.load()
    result = EpgPipeline._canonicalize_guides([guide], registry)
    assert len(result) == 1
    assert result[0].channel_id != "tvn.pl"


def test_orphan_programme_ids_are_not_fuzzy_matched() -> None:
    start = datetime.now(UTC)
    guide = Guide(
        source_id="fixture",
        programmes=[
            Programme(
                channel_id="PolsaT News Extra",
                start=start,
                stop=start + timedelta(hours=1),
                title="Nieznana ramówka",
                source_id="fixture",
            )
        ],
    )
    assert EpgPipeline._canonicalize_guides([guide], ChannelRegistry.load()) == []
