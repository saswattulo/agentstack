.PHONY: help install dev up down logs ps restart \
        api worker beat shell psql redis-cli qdrant-ui phoenix-ui grafana-ui \
        migrate migration test test-unit test-integration lint fmt typecheck \
        clean nuke load-test

help:
	@echo "AgentStack — make targets"
	@echo ""
	@echo "  install        Install Python deps via uv"
	@echo "  dev            uv sync + run API locally (no Docker)"
	@echo "  up             docker compose up -d (all services)"
	@echo "  down           docker compose down"
	@echo "  logs           docker compose logs -f"
	@echo "  ps             docker compose ps"
	@echo "  restart        Restart api + worker"
	@echo ""
	@echo "  api            Tail api logs"
	@echo "  worker         Tail celery worker logs"
	@echo "  shell          Open shell in api container"
	@echo "  psql           Open psql to the agentstack DB"
	@echo "  redis-cli      Open redis-cli"
	@echo "  qdrant-ui      Print Qdrant dashboard URL"
	@echo "  phoenix-ui     Print Phoenix UI URL"
	@echo "  grafana-ui     Print Grafana UI URL"
	@echo ""
	@echo "  migrate        Run alembic upgrade head"
	@echo "  migration M=…  Create new alembic migration (autogenerate)"
	@echo ""
	@echo "  test           Run all tests"
	@echo "  test-unit      Run unit tests only"
	@echo "  test-integration  Run integration tests (requires docker up)"
	@echo "  lint           Run ruff"
	@echo "  fmt            Run ruff format"
	@echo "  typecheck      Run mypy"
	@echo "  load-test      Run locust against http://localhost:8000"
	@echo ""
	@echo "  clean          Remove caches"
	@echo "  nuke           down -v (delete all volumes — destructive)"

install:
	uv sync --all-extras

dev:
	uv sync --all-extras
	uv run uvicorn agentstack.main:app --reload --host 0.0.0.0 --port 8000

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

restart:
	docker compose restart api worker

api:
	docker compose logs -f api

worker:
	docker compose logs -f worker

shell:
	docker compose exec api bash

psql:
	docker compose exec postgres psql -U agentstack -d agentstack

redis-cli:
	docker compose exec redis redis-cli

qdrant-ui:
	@echo "Qdrant dashboard: http://localhost:6333/dashboard"

phoenix-ui:
	@echo "Phoenix UI:      http://localhost:6006"

grafana-ui:
	@echo "Grafana UI:      http://localhost:3001 (admin/admin)"

migrate:
	docker compose exec api alembic upgrade head

migration:
	@if [ -z "$(M)" ]; then echo "Usage: make migration M='your message'"; exit 1; fi
	docker compose exec api alembic revision --autogenerate -m "$(M)"

test:
	uv run pytest

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run mypy src

load-test:
	uv run locust -f tests/load/locustfile.py --host=http://localhost:8000

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml

nuke:
	docker compose down -v
