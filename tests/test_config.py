from pathlib import Path

import pytest

from kr_live_epg.config import load_config
from kr_live_epg.exceptions import ConfigurationError
from kr_live_epg.models import PlaylistKind


def test_load_config_expands_environment_and_resolves_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("M3U_FOR_TEST", "https://provider.example/list.m3u")
    path = tmp_path / "config.yaml"
    path.write_text(
        """
guide_sources:
  - id: fixture
    url: guide.xml
profiles:
  dom:
    playlist:
      type: m3u
      url: ${M3U_FOR_TEST}
storage:
  type: local
  local_directory: generated
""",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.profiles["dom"].playlist.type == PlaylistKind.M3U
    assert config.profiles["dom"].playlist.url == "https://provider.example/list.m3u"
    assert Path(config.storage.local_directory) == tmp_path / "generated"


def test_missing_environment_secret_is_configuration_error(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
guide_sources: [{id: fixture, url: guide.xml}]
profiles:
  dom:
    playlist: {type: m3u, url: '${DOES_NOT_EXIST_ANYWHERE}'}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="DOES_NOT_EXIST_ANYWHERE"):
        load_config(path)


def test_rejects_profile_path_traversal(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
guide_sources: [{id: fixture, url: guide.xml}]
profiles:
  '../outside':
    playlist: {type: none}
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="unsafe profile"):
        load_config(path)
