# Server
start-dev:
	uv run uvicorn app.main:app --reload

start-prod:
	uv run uvicorn app.main:app \
			--host 0.0.0.0 \
			--workers 4 \
			--port 8000

compose-up-dev:
	docker compose -f docker-compose.local.yml up -d

compose-down-dev:
	docker compose -f docker-compose.local.yml down

compose-down-v-dev:
	docker compose -f docker-compose.local.yml down -v

compose-logs-dev:
	docker compose -f docker-compose.local.yml logs -f

compose-ps-dev:
	docker compose -f docker-compose.local.yml ps

db-migrate-new message:
	uv run alembic revision --autogenerate -m "{{message}}"

db-migrate-up:
	uv run alembic upgrade head

db-migrate-down:
	uv run alembic downgrade -1

db-migrate-down-to revision_id:
	uv run alembic downgrade "{{revision_id}}"

db-migrate-reset:
	uv run alembic downgrade base

db-migrate-history:
	uv run alembic history

db-migrate-current:
	uv run alembic current

db-seed:
	uv run python -m app.seeders.runner

test:
	uv run pytest

test-unit:
    uv run pytest app

test-e2e:
    uv run pytest tests

format:
    uv run black .

format-check:
    uv run black --check .
