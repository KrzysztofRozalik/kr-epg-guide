import pytest
from fastapi.testclient import TestClient

from kr_live_epg import service
from kr_live_epg.service import app


def test_delivery_endpoint_requires_profile_token(tmp_path, monkeypatch) -> None:
    output = tmp_path / "output/dom"
    output.mkdir(parents=True)
    (output / "epg.xml").write_text("<?xml version='1.0'?><tv/>", encoding="utf-8")
    (output / "coverage.json").write_text('{"channels": []}', encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
guide_sources: [{{id: fixture, url: guide.xml}}]
profiles:
  dom:
    playlist: {{type: none}}
    delivery_token: very-secret-token
storage:
  type: local
  local_directory: {tmp_path / "output"}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("KR_EPG_CONFIG", str(config))
    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    assert client.get("/v1/dom/epg.xml").status_code == 401
    response = client.get("/v1/dom/epg.xml?token=very-secret-token")
    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("private")
    coverage = client.get("/v1/dom/coverage.json?token=very-secret-token")
    assert coverage.status_code == 200
    assert coverage.json() == {"channels": []}


def test_build_failure_is_reported_to_caller(monkeypatch) -> None:
    class BrokenPipeline:
        def __init__(self, config: object) -> None:
            pass

        def run(self, **kwargs: object) -> list[object]:
            raise RuntimeError("source failed")

    monkeypatch.setattr(service, "_config", lambda: object())
    monkeypatch.setattr(service, "EpgPipeline", BrokenPipeline)

    with pytest.raises(RuntimeError, match="source failed"):
        service._run_build(None, "full")

    assert service._runtime["running"] is False
    assert service._runtime["last_error"] == "source failed"
