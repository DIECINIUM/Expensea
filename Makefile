SHELL := /bin/sh

PYTHON ?= python3
UV_VERSION ?= 0.11.31
VENV := .venv
API_PYTHON := $(VENV)/bin/python
API_PIP := $(VENV)/bin/pip
API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: help setup lock env db-up migrate dev stop dev-api dev-web smoke test test-api test-web lint lint-api lint-web typecheck audit format build check

help:
	@echo "SpendGraph AI development commands"
	@echo "  make setup      Install backend and frontend dependencies"
	@echo "  make lock       Refresh committed Python dependency locks"
	@echo "  make env        Create .env from .env.example when absent"
	@echo "  make dev        Run PostgreSQL, API, and web app with Docker Compose"
	@echo "  make stop       Stop Compose services while preserving data"
	@echo "  make smoke      Verify the local web-to-GraphQL foundation path"
	@echo "  make db-up      Run only PostgreSQL with Docker Compose"
	@echo "  make migrate    Apply Alembic migrations"
	@echo "  make test       Run backend and frontend tests"
	@echo "  make lint       Run all linters and formatting checks"
	@echo "  make typecheck  Run Python and TypeScript type checks"
	@echo "  make audit      Run Python and Node dependency audits"
	@echo "  make build      Build the frontend production bundle"
	@echo "  make check      Run lint, type checks, tests, and build"

env:
	@test -f .env || cp .env.example .env

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(API_PIP) install --upgrade pip

setup: $(VENV)/bin/activate
	$(API_PIP) install -r $(API_DIR)/requirements-dev.lock
	$(API_PIP) install --no-deps -e ./$(API_DIR)
	npm --prefix $(WEB_DIR) ci

$(VENV)/bin/uv: $(VENV)/bin/activate
	$(API_PIP) install "uv==$(UV_VERSION)"

lock: $(VENV)/bin/uv
	$(VENV)/bin/uv pip compile $(API_DIR)/pyproject.toml --universal \
		--python-version 3.12 --output-file $(API_DIR)/requirements.lock \
		--custom-compile-command "make lock"
	$(VENV)/bin/uv pip compile $(API_DIR)/pyproject.toml --extra dev --universal \
		--python-version 3.12 --output-file $(API_DIR)/requirements-dev.lock \
		--custom-compile-command "make lock"

db-up: env
	docker compose up -d db

migrate: env
	$(VENV)/bin/alembic -c $(API_DIR)/alembic.ini upgrade head

dev: env
	docker compose up --build

stop:
	docker compose down

dev-api: env
	@set -a; . ./.env; set +a; \
	exec $(VENV)/bin/uvicorn app.main:app --app-dir $(API_DIR) \
		--host "$${API_HOST:-127.0.0.1}" --port "$${API_PORT:-8000}" --reload

dev-web: env
	@set -a; . ./.env; set +a; \
	exec npm --prefix $(WEB_DIR) run dev -- \
		--host "$${WEB_HOST:-127.0.0.1}" --port "$${WEB_PORT:-5173}"

smoke: env
	@set -a; . ./.env; set +a; \
	exec sh scripts/smoke-foundation.sh

test: test-api test-web

test-api:
	$(VENV)/bin/pytest $(API_DIR)/tests

test-web:
	npm --prefix $(WEB_DIR) run test

lint: lint-api lint-web

lint-api:
	$(VENV)/bin/ruff check $(API_DIR)
	$(VENV)/bin/ruff format --check $(API_DIR)

lint-web:
	npm --prefix $(WEB_DIR) run lint
	npm --prefix $(WEB_DIR) run format:check

typecheck:
	$(VENV)/bin/mypy --config-file $(API_DIR)/pyproject.toml $(API_DIR)/app
	npm --prefix $(WEB_DIR) run typecheck

audit:
	$(VENV)/bin/pip-audit --strict -r $(API_DIR)/requirements.lock
	npm --prefix $(WEB_DIR) audit --omit=dev --audit-level=high

format:
	$(VENV)/bin/ruff check --fix $(API_DIR)
	$(VENV)/bin/ruff format $(API_DIR)
	npm --prefix $(WEB_DIR) run format

build:
	npm --prefix $(WEB_DIR) run build

check: lint typecheck test build audit
