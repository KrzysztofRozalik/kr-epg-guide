from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from .config import load_config
from .normalize import normalize_channel_name
from .pipeline import EpgPipeline
from .writer import validate_xmltv

app = typer.Typer(
    name="kr-live-epg",
    help="Agregator XMLTV z normalizacją nazw i szybkimi korektami ramówki.",
    no_args_is_help=True,
)


@app.command()
def build(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", exists=True),
    profile: list[str] | None = typer.Option(None, "--profile", "-p"),
    mode: str = typer.Option("full", help="Etykieta przebiegu: full albo live."),
) -> None:
    """Pobierz źródła, dopasuj kanały i atomowo opublikuj wynik."""

    try:
        results = EpgPipeline(load_config(config)).run(profiles=profile, mode=mode)
    except Exception as exc:
        typer.secho(f"BŁĄD: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    for result in results:
        typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))


@app.command("normalize")
def normalize_name(name: str) -> None:
    """Pokaż wynik czyszczenia nazwy kanału bez modyfikacji plików."""

    result = normalize_channel_name(name)
    typer.echo(
        json.dumps(
            {
                "raw": result.raw,
                "normalized": result.normalized,
                "numbers": result.numbers,
                "semantic_tokens": result.semantic_tokens,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("validate")
def validate(path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    """Sprawdź spójność gotowego XMLTV lub XMLTV.GZ."""

    try:
        validate_xmltv(path)
    except Exception as exc:
        typer.secho(f"NIEPOPRAWNY: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho("POPRAWNY", fg=typer.colors.GREEN)


@app.command()
def serve(
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", exists=True),
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8080, min=1, max=65535),
) -> None:
    """Uruchom HTTP API i serwowanie wygenerowanych plików."""

    import uvicorn

    os.environ["KR_EPG_CONFIG"] = str(config.resolve())
    uvicorn.run("kr_live_epg.service:app", host=host, port=port, reload=False, access_log=False)


if __name__ == "__main__":
    app()
