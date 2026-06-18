# Server
start-dev:
	uv run python -m uvicorn app.main:app --reload

start-prod:
	uv run python -m uvicorn app.main:app \
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
	uv run python -m alembic revision --autogenerate -m "{{message}}"

db-migrate-up:
	uv run python -m alembic upgrade head

db-migrate-down:
	uv run python -m alembic downgrade -1

db-migrate-down-to revision_id:
	uv run python -m alembic downgrade "{{revision_id}}"

db-migrate-reset:
	uv run python -m alembic downgrade base

db-migrate-history:
	uv run python -m alembic history

db-migrate-current:
	uv run python -m alembic current

db-seed:
	PYTHONPATH=. uv run python scripts/seed_db.py

test:
	uv run python -m pytest

test-unit:
    uv run python -m pytest app

test-e2e:
    uv run python -m pytest tests

celery-worker:
	uv run celery -A app.config.celery worker --loglevel=info -E

celery-active:
    uv run celery -A app.config.celery inspect active

celery-stats:
    uv run celery -A app.config.celery inspect stats

celery-purge:
    uv run celery -A app.config.celery purge -f

celery-flower:
    uv run python -m flower -A app.config.celery flower --port=5555 --address=0.0.0.0

lint:
	uv run ruff check .

lint-app:
	uv run black --check app/

lint-fix:
	uv run ruff check . --fix

format:
	uv run ruff format .

format-check:
	uv run ruff format . --check

# Run all checks (linting and formatting)
check:
	just lint
	just lint-app
	just format-check

# Redis utilities
redis-keys pattern="*":
	redis-cli KEYS "{{pattern}}"

redis-get key:
	redis-cli GET "{{key}}"

redis-scan pattern="*":
	redis-cli --scan --pattern "{{pattern}}" | head -100

redis-flush-pattern pattern="*":
	redis-cli KEYS "{{pattern}}" | xargs redis-cli DEL

redis-version-search-keys:
    echo "=== content keys ===" && \
    redis-cli --scan --pattern "content*" | head -50 && \
    echo "=== Version keys ===" && \
    redis-cli --scan --pattern "version*" | head -50 && \
    echo "=== Search keys ===" && \
    redis-cli --scan --pattern "search:*" | head -50

get-gemini-model-list:
	uv run python scratch/list_models.py