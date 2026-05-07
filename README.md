# AIPCPP-Mahi-Onboarding
Build an automated ingestion pipeline that parses files, uses AI for summaries/tagging, and stores data in a searchable index, all managed via asynchronous task queues for scalability.

## Installation

Install these tools first:

1. [Python 3.12.3](https://www.python.org/downloads/release/python-3123/)
2. [uv](https://docs.astral.sh/uv/getting-started/installation/)
3. [just](https://github.com/casey/just#installation)
4. [Docker Engine / Docker Desktop](https://docs.docker.com/get-docker/)
5. [Docker Compose plugin](https://docs.docker.com/compose/install/)

Optional but recommended:
- [Git](https://git-scm.com/downloads)

## Project setup

Clone and enter the project:

```bash
git clone <your-repo-url>
cd AIPCPP-Mahi-Onboarding
```

Use the project Python version:

```bash
python --version
# expected: 3.12.3
```

Create environment file:

```bash
cp .env.example .env
```

Install dependencies:

```bash
uv sync
```

Start local databases (dev on `5432`, test on `5433`) and Redis:

```bash
just compose-up-dev
```

Apply migrations:

```bash
just db-migrate-up
```

## Running the app

Development mode (hot reload):

```bash
just start-dev
```

Production mode (with workers):

```bash
just start-prod
```

App URLs:

- API base: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Testing

Run all tests:

```bash
just test
```

Run targeted test commands with `uv`:

```bash
uv run pytest app/modules/
uv run pytest app/modules/<module>/tests/
uv run pytest app/modules/<module>/tests/test_file.py
uv run pytest app/modules/<module>/tests/test_file.py::test_name
```

## Database and migrations

Create new autogenerate migration:

```bash
just db-migrate-new "your migration message"
```

Migration commands:

```bash
just db-migrate-up
just db-migrate-down
just db-migrate-down-to <revision_id>
just db-migrate-reset
just db-migrate-history
just db-migrate-current
```

## Docker compose helpers

```bash
just compose-up-dev
just compose-down-dev
just compose-down-v-dev
just compose-logs-dev
just compose-ps-dev
```

## Common local workflow

```bash
uv sync
cp .env.example .env
just compose-up-dev
just db-migrate-up
just start-dev
```

In another terminal:

```bash
just test
```

## Documentation

- [Summary Generation Pipeline](docs/summary_generation_pipeline.md): Detailed guide on the background processing workflow, AI analysis, and vector embeddings.
- [Upload API Walkthrough](docs/upload_api_walkthrough.md): Guide for integrating the file upload API.

## Troubleshooting

- If `docker compose` fails, verify Docker daemon is running.
- If port `5432`, `5433` or `6379` is busy, stop local PostgreSQL/Redis services or remap ports in `docker-compose.local.yml`.
- If app fails on startup due to config, verify `.env` exists and values are set correctly.
