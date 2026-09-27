from kr_live_epg.m3u import parse_m3u, render_m3u

M3U = """#EXTM3U
#EXTINF:-1 tvg-id="raw.ps1" tvg-name="[PL] Polsat Sport 1 HD" tvg-logo="logo.png" group-title="Sport" catchup="default" catchup-days="7" catchup-source="https://archive.example/{start}",[PL] Polsat Sport 1 HD
#EXTVLCOPT:http-referrer=https://example.test/
https://stream.example.test/secret
"""


def test_parse_and_render_normalized_m3u() -> None:
    channels = parse_m3u(M3U)
    assert len(channels) == 1
    assert channels[0].tvg_id == "raw.ps1"
    assert channels[0].stream_url == "https://stream.example.test/secret"
    channels[0].canonical_id = "polsat-sport-1.pl"
    channels[0].canonical_name = "Polsat Sport 1"
    rendered = render_m3u(channels, xmltv_url="https://epg.example/v1/dom/epg.xml.gz")
    assert 'tvg-id="polsat-sport-1.pl"' in rendered
    assert ",Polsat Sport 1\n" in rendered
    assert "#EXTVLCOPT:http-referrer=" in rendered
    assert 'catchup="default"' in rendered
    assert 'catchup-days="7"' in rendered
    assert 'catchup-source="https://archive.example/{start}"' in rendered
    assert "https://stream.example.test/secret" in rendered
