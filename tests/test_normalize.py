import pytest

from kr_live_epg.normalize import normalize_channel_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Polsat Sport 1 HD [PL]", "polsat sport 1"),
        ("[PL] | CANAL+ SPORT 2 FHD 50FPS", "canal plus sport 2"),
        ("POL: HBO 2 UHD HEVC", "hbo 2"),
        ("{PL} TVN24 (FULL HD)", "tvn24"),
        ("VIP | Eleven Sports 1 4K", "eleven sports 1"),
        ("PL| CANAL+ 4K ULTRA HD", "canal plus 4k"),
        ("PL-VIP| CANAL+ 4K FHD", "canal plus 4k"),
        ("CANAL+ SPORT 4K PL", "canal plus sport"),
        ("PL | Travelxp 4K FHD", "travelxp 4k"),
        ("Sky Sports F1 UHD [VIP]", "sky sports f1 uhd"),
        ("4FUN TV", "4fun tv"),
        ("Kino Polska Muzyka", "kino polska muzyka"),
    ],
)
def test_normalize_provider_decorations(raw: str, expected: str) -> None:
    assert normalize_channel_name(raw).normalized == expected


def test_semantic_channel_number_is_preserved() -> None:
    one = normalize_channel_name("Polsat Sport 1 HD")
    two = normalize_channel_name("Polsat Sport 2 FHD")
    assert one.numbers == ("1",)
    assert two.numbers == ("2",)
    assert one.normalized != two.normalized
