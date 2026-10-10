SHELL := /bin/sh

PYTHON ?= python3
UV_VERSION ?= 0.11.31
VENV := .venv
API_PYTHON := $(VENV)/bin/python
API_PIP := $(VENV)/bin/pip
API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: help setup lock env db-up bootstrap migrate seed dev stop dev-api dev-web worker smoke test test-api test-web lint lint-api lint-web typecheck audit format build eval-extraction eval-reconciliation eval-categorization eval-agent check prod-config prod prod-stop prod-smoke backup restore

help:
	@echo "SpendGraph AI development commands"
	@echo "  make setup      Install backend and frontend dependencies"
	@echo "  make lock       Refresh committed Python dependency locks"
	@echo "  make env        Create .env from .env.example when absent"
	@echo "  make dev        Run PostgreSQL, API, and web app with Docker Compose"
	@echo "  make stop       Stop Compose services while preserving data"
	@echo "  make smoke      Verify the local web-to-GraphQL foundation path"
	@echo "  make db-up      Run only PostgreSQL with Docker Compose"
	@echo "  make bootstrap  Apply migrations and seed the development ledger"
	@echo "  make migrate    Apply Alembic migrations in Docker"
	@echo "  make seed       Idempotently seed the development ledger"
	@echo "  make test       Run backend and frontend tests"
	@echo "  make lint       Run all linters and formatting checks"
	@echo "  make typecheck  Run Python and TypeScript type checks"
	@echo "  make audit      Run Python and Node dependency audits"
	@echo "  make build      Build the frontend production bundle"
	@echo "  make eval-extraction  Evaluate configured AI on labelled synthetic notes"
	@echo "  make eval-reconciliation  Evaluate deterministic duplicate decisions"
	@echo "  make eval-categorization  Evaluate deterministic correction retrieval"
	@echo "  make eval-agent  Evaluate read-only agent routing, facts, grounding and safety"
	@echo "  make check      Run lint, type checks, tests, and build"
	@echo "  make worker     Run the durable-job worker locally"
	@echo "  make prod-config  Validate .env.production and production Compose"
	@echo "  make prod       Start production containers (requires configured OIDC/database/domain)"
	@echo "  make prod-stop  Stop production containers without deleting volumes"
	@echo "  make prod-smoke DEPLOYMENT_URL=https://host  Verify deployed HTTPS services"
	@echo "  make backup BACKUP_PATH=path  Back up the privately configured PG* database"
	@echo "  make restore BACKUP_PATH=path  Restore to a new spendgraph_restore_* database"

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
	docker compose run --rm migrate alembic -c alembic.ini upgrade head

seed: env
	docker compose run --rm migrate python -m app.seed

bootstrap: env
	docker compose run --rm migrate

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

worker: env
	@set -a; . ./.env; set +a; \
	PYTHONPATH=$(API_DIR) exec $(API_PYTHON) -m app.jobs.worker

prod-config:
	@test -f .env.production || { echo "Configure the ignored .env.production first."; exit 1; }
	docker compose --env-file .env.production -f docker-compose.production.yml config --quiet

prod: prod-config
	docker compose --env-file .env.production -f docker-compose.production.yml up --build -d

prod-stop:
	docker compose --env-file .env.production -f docker-compose.production.yml down

prod-smoke:
	@test -n "$(DEPLOYMENT_URL)" || { echo "Set DEPLOYMENT_URL=https://your-host"; exit 1; }
	sh scripts/smoke-deployment.sh "$(DEPLOYMENT_URL)"

backup:
	sh scripts/backup-database.sh "$(BACKUP_PATH)"

restore:
	sh scripts/restore-database.sh "$(BACKUP_PATH)"

smoke: env
	@set -a; . ./.env; set +a; \
	exec sh scripts/smoke-foundation.sh

test: test-api test-web

test-api: env
	docker compose up -d --wait db
	@set -a; . ./.env; set +a; \
	APP_ENV=test APP_DEBUG=false RUN_DATABASE_TESTS=1 \
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

eval-extraction: env
	@set -a; . ./.env; set +a; \
	PYTHONPATH=$(API_DIR) $(API_PYTHON) evals/run_extraction.py \
		--dataset evals/extraction/v1.jsonl

eval-reconciliation:
	@PYTHONPATH=$(API_DIR) $(API_PYTHON) evals/run_reconciliation.py \
		--dataset evals/reconciliation/v1.jsonl

eval-categorization:
	@PYTHONPATH=$(API_DIR) $(API_PYTHON) evals/run_categorization.py \
		--dataset evals/categorization/v1.jsonl

eval-agent:
	$(API_PYTHON) evals/agent/run.py

check: lint typecheck test build audit
