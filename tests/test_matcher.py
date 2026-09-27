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
