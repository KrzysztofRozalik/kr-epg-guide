from kr_live_epg.matcher import ChannelMatcher
from kr_live_epg.models import CanonicalChannel, Channel
from kr_live_epg.registry import ChannelRegistry


def _channel(name: str) -> Channel:
    return Channel(source_id="test", provider_id="999", name=name)


def test_matches_heavily_decorated_name() -> None:
    registry = ChannelRegistry([CanonicalChannel(id="polsat-sport-1.pl", name="Polsat Sport 1")])
    match = ChannelMatcher(registry).match(_channel("[PL] | POLSAT SPORT 1 FHD 50FPS"))
    assert match.canonical_id == "polsat-sport-1.pl"
    assert match.score == 100


def test_never_confuses_channel_numbers() -> None:
    registry = ChannelRegistry([CanonicalChannel(id="polsat-sport-1.pl", name="Polsat Sport 1")])
    match = ChannelMatcher(registry, threshold=60, margin=0).match(_channel("Polsat Sport 2 HD"))
    assert match.canonical_id is None


def test_dedicated_4k_station_is_not_generic_canal_plus() -> None:
    registry = ChannelRegistry(
        [
            CanonicalChannel(id="canal-plus.pl", name="Canal+"),
            CanonicalChannel(id="canal-plus-4k.pl", name="Canal+ 4K Ultra HD"),
        ]
    )
    matcher = ChannelMatcher(registry)
    assert matcher.match(_channel("PL| CANAL+ 4K ULTRA HD")).canonical_id == "canal-plus-4k.pl"
    assert matcher.match(_channel("Canal+ HD")).canonical_id == "canal-plus.pl"
    assert ChannelMatcher._score("Canal+", "Canal+ 4K Ultra HD") == 0


def test_predecessor_id_can_resolve_rebrand() -> None:
    registry = ChannelRegistry(
        [
            CanonicalChannel(
                id="new-channel.pl",
                name="Nowy Kanał",
                predecessor_ids=["old-channel.pl"],
            )
        ]
    )
    channel = Channel(
        source_id="provider",
        provider_id="22",
        tvg_id="old-channel.pl",
        name="Nazwa od operatora",
    )
    assert ChannelMatcher(registry).match(channel).canonical_id == "new-channel.pl"


def test_photo_examples_match_rebrands_and_decorated_event_channels() -> None:
    registry = ChannelRegistry.load()
    matcher = ChannelMatcher(registry)
    examples = {
        "PL | FOX COMEDY FHD [50FPS]": "fx-comedy.pl",
        "{PL} FOX 4K HEVC": "fx.pl",
        "[PL] MTV 80's FULL HD": "mtv-80s.pl",
        "VIP: CANAL+ LIVE 4 UHD": "canal-plus-live-4.pl",
        "PL | PPV EVENT FIGHT 2 HD": "ppv-event-fight-2.pl",
        "[POL] VIAPLAY-PL 5 FHD": "viaplay-5.pl",
    }
    for name, expected in examples.items():
        assert matcher.match(_channel(name)).canonical_id == expected


def test_tvp3_local_stations_keep_their_regional_identity() -> None:
    registry = ChannelRegistry.load()
    matcher = ChannelMatcher(registry)
    examples = {
        "PL | TVP 3 Wrocław FHD": "tvp-3-wroclaw.pl",
        "[POL] TVP3 BIALYSTOK HD": "tvp-3-bialystok.pl",
        "TVP 3 Gorzów Wlkp. VIP PL": "tvp-3-gorzow-wielkopolski.pl",
        "PL: TVP 3 Łódź 1080p": "tvp-3-lodz.pl",
        "TVP3 Olsztyn/Elbląg": "tvp-3-olsztyn.pl",
        "TVP 3": "tvp-3.pl",
    }
    for name, expected in examples.items():
        assert matcher.match(_channel(name)).canonical_id == expected
