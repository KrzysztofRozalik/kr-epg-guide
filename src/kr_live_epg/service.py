from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse

from . import __version__
from .config import AppConfig, load_config
from .pipeline import EpgPipeline

app = FastAPI(
    title="KR Live EPG",
    version=__version__,
    docs_url=None,
    redoc_url=None,
)
_run_lock = threading.Lock()
_runtime_lock = threading.Lock()
_runtime: dict[str, object] = {"running": False, "last_error": None}


def _config() -> AppConfig:
    return load_config(os.environ.get("KR_EPG_CONFIG", "config.yaml"))


def _profile(config: AppConfig, name: str) -> object:
    profile = config.profiles.get(name)
    if profile is None:
        raise HTTPException(status_code=404, detail="Nieznany profil")
    return profile


def _authorise_delivery(
    expected: object,
    token: str | None,
    authorization: str | None,
) -> None:
    expected_value = expected.get_secret_value() if expected else ""  # type: ignore[union-attr]
    if not expected_value:
        return
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else ""
    supplied = token or bearer
    if not supplied or not secrets.compare_digest(supplied, expected_value):
        raise HTTPException(status_code=401, detail="Nieprawidłowy token")


def _file(
    profile_name: str,
    filename: str,
    token: str | None,
    authorization: str | None,
) -> FileResponse:
    config = _config()
    profile = _profile(config, profile_name)
    _authorise_delivery(profile.delivery_token, token, authorization)  # type: ignore[attr-defined]
    path = Path(config.storage.local_directory) / profile_name / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Plik nie został jeszcze wygenerowany")
    media_types = {
        "epg.xml": "application/xml",
        "epg.xml.gz": "application/gzip",
        "playlist.m3u": "application/vnd.apple.mpegurl",
        "status.json": "application/json",
        "coverage.json": "application/json",
    }
    protected = bool(profile.delivery_token and profile.delivery_token.get_secret_value())  # type: ignore[attr-defined]
    cache_control = (
        "private, max-age=60, stale-while-revalidate=300"
        if protected
        else "public, max-age=60, stale-while-revalidate=300"
    )
    return FileResponse(
        path,
        media_type=media_types[filename],
        headers={"Cache-Control": cache_control, "Vary": "Authorization"},
    )


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def ready(response: Response) -> dict[str, object]:
    try:
        config = _config()
        generated = any(
            (Path(config.storage.local_directory) / name / "status.json").is_file()
            for name in config.profiles
        )
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"ready": False, "error": str(exc)}
    if not generated:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ready": generated, **_runtime}


@app.get("/v1/{profile_name}/epg.xml")
def epg_xml(
    profile_name: str,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> FileResponse:
    return _file(profile_name, "epg.xml", token, authorization)


@app.get("/v1/{profile_name}/epg.xml.gz")
def epg_gzip(
    profile_name: str,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> FileResponse:
    return _file(profile_name, "epg.xml.gz", token, authorization)


@app.get("/v1/{profile_name}/playlist.m3u")
def playlist(
    profile_name: str,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> FileResponse:
    return _file(profile_name, "playlist.m3u", token, authorization)


@app.get("/v1/{profile_name}/status.json")
def build_status(
    profile_name: str,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> FileResponse:
    return _file(profile_name, "status.json", token, authorization)


@app.get("/v1/{profile_name}/coverage.json")
def coverage_report(
    profile_name: str,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
) -> FileResponse:
    return _file(profile_name, "coverage.json", token, authorization)


def _run_build(profile_names: list[str] | None, mode: str) -> list[dict[str, object]]:
    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("Generowanie już trwa")
    try:
        with _runtime_lock:
            _runtime["running"] = True
            _runtime["last_error"] = None
        results = EpgPipeline(_config()).run(profiles=profile_names, mode=mode)
        return [item.model_dump(mode="json") for item in results]
    except Exception as exc:
        with _runtime_lock:
            _runtime["last_error"] = str(exc)
        raise
    finally:
        with _runtime_lock:
            _runtime["running"] = False
        _run_lock.release()


@app.post("/admin/run")
def trigger_build(
    profile: list[str] | None = Query(default=None),
    mode: str = Query(default="full", pattern="^(full|live)$"),
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> dict[str, object]:
    expected = os.environ.get("KR_EPG_ADMIN_TOKEN", "")
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else ""
    supplied = x_admin_token or bearer
    if not expected:
        raise HTTPException(status_code=503, detail="Zdalne uruchamianie jest wyłączone")
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Nieprawidłowy token administratora")
    if _run_lock.locked():
        raise HTTPException(status_code=409, detail="Generowanie już trwa")
    try:
        results = _run_build(profile, mode)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"completed": True, "profiles": profile or "all", "mode": mode, "results": results}
