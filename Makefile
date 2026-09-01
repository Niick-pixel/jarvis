# Jarvis - a local-first AI workspace.
# Everything binds 127.0.0.1. Nothing here talks to a network service you did not start.

PY := .venv/bin/python
UV := $(shell command -v uv 2>/dev/null)
API_HOST ?= 127.0.0.1
API_PORT ?= 8080

.DEFAULT_GOAL := help
.PHONY: help dev check models bench types install web-install voice voice-install searxng clean

help:
	@echo "make dev      start llama-server (if autostart), the backend and the frontend"
	@echo "make check    lint, types, tests, schema drift, file length, contrast, no-phone-home"
	@echo "make models   rank what fits your card, download it, register it"
	@echo "make bench    measure model tok/s and the background's GPU cost against the 3% budget"
	@echo "make types    regenerate web/src/api/schema.gen.ts from the OpenAPI schema"
	@echo "make voice    download the STT model and one TTS voice into ./models"
	@echo "make searxng  install a local SearXNG for private web search (no Docker)"

.venv:
ifndef UV
	$(error uv is not installed. See https://docs.astral.sh/uv/ - or create .venv yourself)
endif
	uv venv --python 3.12 .venv

install: .venv
	uv pip install --python .venv/bin/python -e ".[dev]"

web-install:
	cd web && npm install --no-audit --no-fund

dev: install web-install
	@$(PY) -c "from server.db.connection import Database; from server.db.migrate import migrate; \
from server.settings import load_settings; s = load_settings(); d = Database(s.paths.db_path); \
c = d.connect(); print('migrations:', migrate(c) or 'up to date')"
	@echo "backend  http://$(API_HOST):$(API_PORT)"
	@echo "frontend http://127.0.0.1:5173   (open this one)"
	@trap 'kill 0' EXIT INT TERM; \
	$(PY) -m uvicorn server.main:app --host $(API_HOST) --port $(API_PORT) & \
	(cd web && npm run dev) & \
	wait

check: install
	.venv/bin/ruff format --check server scripts tests
	.venv/bin/ruff check server scripts tests
	.venv/bin/mypy
	$(PY) -m pytest -q
	cd web && npm run test
	$(PY) scripts/gen_types.py --check
	cd web && npx tsc -b --noEmit
	cd web && npm run build
	$(PY) scripts/contrast_check.py
	$(PY) scripts/checks.py

models: install
	$(PY) scripts/models_cli.py

bench: install
	$(PY) scripts/gpu_budget.py

types: install
	$(PY) scripts/gen_types.py

voice-install: .venv
	uv pip install --python .venv/bin/python -e ".[voice]"

voice: install
	$(PY) scripts/voice_cli.py

searxng:
	./scripts/setup_searxng.sh

clean:
	rm -rf .venv web/node_modules web/dist .pytest_cache .mypy_cache .ruff_cache
