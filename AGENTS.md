## Common Commands

All commands use `uv run` — do not use bare `python` or `pip`.

## Architecture

**Stack:** FastAPI + SQLModel (SQLAlchemy + Pydantic) + PostgreSQL (async via asyncpg) + Alembic + uv package manager. Python 3.12.3.

**Layered module pattern** — each feature is a self-contained module under `app/modules/<domain>/`:

```
app/modules/<domain>/
├── __init__.py
├── repositories.py   # Data access — accepts AsyncSession in constructor
├── constants.py      # Reusable Constants and Error details
├── services.py       # Business logic, wraps repository
├── routes.py         # HTTP handlers (if the module has endpoints)
├── schemas.py        # Request/response Pydantic models (if needed)
└── tests/            # Module-specific tests
    ├── __init__.py
    └── test_*.py
```

**Database sessions:** Injected via `Depends(get_db_session)` using async `AsyncSession`. Engine and session factory live in `app/config/db.py`. `AsyncSessionLocal` uses `expire_on_commit=False`.

**Configuration:** `app/config/settings.py` uses pydantic-settings with `UPPER_SNAKE_CASE` field names, loading from `.env` (gitignored; see `.env.example`).

**Docker Compose** (`docker-compose.local.yml`) provides two PostgreSQL 17 containers: dev DB on port 5432, test DB on port 5433.

### Repository Pattern

Repositories accept `AsyncSession` in the constructor — methods do not take session as a parameter. Repositories use `flush()` for immediate persistence without committing:

```python
class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user
```

### Service Pattern

Services fall into two categories:

**Session-scoped services** take `AsyncSession` and instantiate repositories:

```python
class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_service = UserService(session)
        self.account_service = AccountService(session)
```

**Stateless services** don't take a session — they're utility classes:

```python
class SecurityService:
    def __init__(self) -> None:
        self._pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

Services that coordinate multiple repositories call `await self.session.commit()` explicitly. Repositories only `flush()`.

### Cross-Module Access

Modules access other modules' data through **services**, not repositories directly:

```python
# Correct — AuthService uses UserService
from app.modules.users.services import UserService

# Wrong — don't import repositories from other modules
from app.modules.users.repositories import UserRepository
```

Keep HTTP logic out of services/repositories. Keep business logic out of routes.

### Schemas

Request/response models live in `app/modules/<domain>/schemas.py` using plain Pydantic `BaseModel`. Table models in `app/models/` can also define inline request/response schemas.

## Code Style

- **Python 3.12+ syntax**: use `str | None` not `Optional[str]`, `list[str]` not `List[str]`, `X | Y` unions
- **All function params and return types** must be annotated

### Naming Conventions

| Item                               | Convention                         | Example                   |
| ---------------------------------- | ---------------------------------- | ------------------------- |
| Modules / files                    | `snake_case`                       | `user_service.py`         |
| Classes                            | `PascalCase`                       | `UserRepository`          |
| Functions / methods                | `snake_case`                       | `get_current_user()`      |
| Constants                          | `UPPER_SNAKE_CASE`                 | `SECRET_KEY`              |
| Pydantic models (request/response) | `TPascalCase` (`T` prefix)         | `TUserCreate`, `TUserRead`|
| SQLModel table models              | `PascalCase`, no suffix            | `User`, `Post`            |
| Routers                            | named `router` in each `routes.py` | `router = APIRouter(...)` |
| Settings fields                    | `UPPER_SNAKE_CASE`                 | `DB_HOST`, `SECRET_KEY`   |


### Error Handling

- Raise `HTTPException` for expected HTTP errors in routes/services
- Use `status` module for status codes: `status.HTTP_404_NOT_FOUND`
- Do not let SQLAlchemy exceptions propagate to the HTTP layer unhandled
- Define Errors in the `constants.py` and use them in `HTTPException` detail

### Testing

- Module-specific `tests/constants.py` files hold test data — no raw strings in test code
- Fixtures use `@pytest.fixture` to instantiate services

#### Module unit/integration tests (`app/modules/<domain>/tests/`)

- File layout: keep tests in `app/modules/<domain>/tests/` with `test_*.py` and sibling `constants.py`
- Helpers: place shared setup/build/assert/patch logic in `app/modules/<domain>/tests/helpers.py`; keep only test cases in `test_*.py`
- Scope: test repositories/services/helpers in isolation with DB fixture support from root `conftest.py`
- Pattern: instantiate repository/service inside each test (or fixture), inject `db_session`, and assert persisted state when relevant
- Organization: class-based grouping by method/behavior (`TestCreate`, `TestGetByEmail`, `TestSignUp`, `TestSignIn`)
- Test data: always pull literals from `app/modules/<domain>/tests/constants.py`
- Mocking: use `monkeypatch` only for side effects or nondeterministic collaborators (email provider, token generation, external calls)
- Assertions: check both return values and DB side effects for write paths (records, timestamps, relation rows)
- Duplication rule: if setup/assertion/patch block repeated in 2+ tests, extract helper function

#### E2E endpoint tests (`tests/<domain>/`)

- File layout: `tests/<domain>/test_<domain>_e2e.py` plus `tests/<domain>/constants.py`; add `tests/<domain>/helpers.py` when shared test utilities grow
- Client fixture pattern (required):
  - override `get_db_session` via `app.dependency_overrides`
  - use `ASGITransport(app=app)` + `AsyncClient(base_url="http://testserver")`
- Use helper builders for payloads/headers/tokens to keep tests short and DRY
- Keep endpoint intent in tests; move reusable helpers (auth header builder, sign-up bootstrap, JWT payload/token builders, repeated response assertions) to `tests/<domain>/helpers.py`
- Group tests by endpoint and outcome (`Test<Endpoint>Success`, `Test<Endpoint>Unauthorized`, `Test<Endpoint>Validation`, etc.)
- Keep expected messages in `tests/<domain>/constants.py` and assert strict `detail` only for app-generated errors
- Cover minimum matrix per protected endpoint:
  - happy path response shape and key fields
  - unauthorized variants (invalid token, expired token, wrong token type, missing claims, user not found)
  - validation failures for malformed/missing request body where applicable
