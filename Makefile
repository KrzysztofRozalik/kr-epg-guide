.PHONY: install format lint test check build serve

install:
	./scripts/install.sh

format:
	.venv/bin/ruff format src tests

lint:
	.venv/bin/ruff check src tests

test:
	.venv/bin/pytest --cov=kr_live_epg --cov-report=term-missing

check:
	.venv/bin/ruff format --check src tests
	.venv/bin/ruff check src tests
	.venv/bin/pytest

build:
	.venv/bin/kr-live-epg build --config config.yaml

serve:
	.venv/bin/kr-live-epg serve --config config.yaml
