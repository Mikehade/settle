# Architecture

A layered, dependency-injected FastAPI service. Business logic depends on **interfaces**; the
container decides which **implementations** it gets.

## 1. Layers and the dependency rule

```
           ┌──────────┐
 HTTP ───► │   api    │  routers, schemas, middleware, exception handlers
           └────┬─────┘
                ▼
           ┌──────────┐
           │   core   │  business logic, one module per domain
           └────┬─────┘
                ▼
           ┌──────────┐            ┌──────────────────┐
           │  domain  │ ◄───────── │  infrastructure  │  DB, repositories, technical services
           └──────────┘ implements └──────────────────┘

 config/container.py builds infrastructure and injects it into core.
 shared/ (logging, error codes, response envelope, utils) is usable from every layer.
```

| Layer | May import | Must never import |
|---|---|---|
| `domain` | `shared` | `core`, `infrastructure`, `api`, `config` |
| `core` | `domain`, `shared` | `infrastructure`, `api`, `config` |
| `infrastructure` | `domain`, `shared` | `core`, `api` |
| `api` | `core`, `domain`, `shared`, `config` | `infrastructure` (directly) |
| `config` | everything: it wires the app | n/a |
| `shared` | stdlib + third-party | anything in `src` |

Enforced by import-linter contracts in `pyproject.toml`. Run `python manage.py lint`.

## 2. Layout

```
├── main.py                     # composition root: app, middleware, routers, handlers
├── manage.py                   # project CLI
├── alembic/                    # async env.py; models discovered automatically
├── scripts/                    # scaffold.py + templates for startapp, seed.py
├── tests/                      # conftest.py (app, client fixtures), unit/, integration/
└── src/
    ├── api/
    │   ├── router.py           # includes every domain router            [kit markers]
    │   ├── deps.py             # typed DI aliases, pagination, auth deps  [kit markers]
    │   ├── exception_handlers.py
    │   ├── middleware/request_context.py   # request id + access log
    │   ├── health/router.py    # /health (liveness), /health/ready (readiness)
    │   └── <domain>/{router.py, schemas.py}
    ├── core/
    │   ├── health.py
    │   └── <domain>.py         # <Entity>Service
    ├── domain/
    │   ├── entities/           # TypedDicts that cross layers; common.Page
    │   ├── interfaces/
    │   │   ├── repositories/<domain>.py   # <Entity>RepositoryInterface (Protocol)
    │   │   ├── services.py                # interfaces for infra services core uses
    │   │   └── uow.py                     # UnitOfWorkInterface, UnitOfWorkFactory
    │   └── exceptions.py       # AppError hierarchy
    ├── infrastructure/
    │   ├── db/
    │   │   ├── base.py         # Base (registry), Model (UUID id + timestamps), mixins
    │   │   ├── session.py      # Database: engine, sessions, ping
    │   │   ├── uow.py          # UnitOfWork
    │   │   └── models/<domain>.py
    │   ├── repositories/
    │   │   ├── base.py         # BaseRepository: session handling, _paginate
    │   │   └── <domain>.py     # Sql<Entity>Repository
    │   └── services/           # technical services: token, hasher, storage, email...
    ├── config/
    │   ├── __init__.py         # get_settings(): picks the class by APP_ENV
    │   ├── base.py             # every setting; required ones have no default
    │   ├── development.py / staging.py / production.py / test.py
    │   └── container.py        # the single DI container                  [kit markers]
    └── shared/
        ├── logging/            # configure_logging, get_logger, JSON/console formatters
        ├── errors/codes.py     # ErrorCode registry                        [kit markers]
        ├── responses.py        # Envelope, success(), paginated(), error_body()
        └── utils/
```

## 3. Where does it go?

| Need | Location |
|---|---|
| Request/response shape | `api/<domain>/schemas.py` |
| Endpoint | `api/<domain>/router.py` (parse → call core → `success()`) |
| Business rule, use case, transaction boundary | `core/<domain>.py` |
| What core may ask of a repository or service | `domain/interfaces/` |
| Data shape passed between layers | `domain/entities/<domain>.py` (TypedDict) |
| Table | `infrastructure/db/models/<domain>.py` |
| Query | `infrastructure/repositories/<domain>.py` |
| External system (JWT, S3, email, Redis, HTTP API) | `infrastructure/services/` |
| Setting | `config/base.py`, overridden per environment |
| Wiring | `config/container.py` |

## 4. Dependency injection

Injection is used throughout. It keeps core free of infrastructure and makes every class
testable with fakes.

1. **The container is the only place objects are built.** No class constructs its own
   dependencies or calls `get_settings()`.
2. **Constructor injection, typed against interfaces.** Core takes `Protocol`s from
   `domain/interfaces/`. Infrastructure may take concrete types.
3. **Settings are injected as values** (`secret_key=config.provided.SECRET_KEY`).
4. **No service locator.** Only `api/deps.py`, `main.py`, `manage.py` and tests touch the container.
5. **One container**, in fixed sections: Resources → Infra services → Unit of work →
   Repositories → Core. Split it by layer only if it passes about 300 lines.

```python
class Container(containers.DeclarativeContainer):
    config = providers.Singleton(get_settings)

    # ---- Resources
    database = providers.Singleton(Database, url=config.provided.DATABASE_URL, ...)

    # ---- Unit of work
    uow = providers.Factory(UnitOfWork, db=database)

    # ---- Repositories
    order_repository = providers.Singleton(SqlOrderRepository, db=database)

    # ---- Core
    order_service = providers.Singleton(OrderService, orders=order_repository, uow=uow.provider)
```

| Provider | Use for |
|---|---|
| `Singleton` | Services, repositories, clients, `Database` |
| `Factory` | New object per use: `UnitOfWork` (injected as `uow.provider`, a factory) |
| `Resource` | Sync setup/teardown only |

Async teardown (engine, Redis pool) happens in `main.py`'s lifespan. Async `Resource`s are
avoided: they turn every dependent provider into an awaitable.

**Routers** use typed aliases from `api/deps.py`; handlers using them need `@inject`.
`main.py` wires `packages=["src.api"]`, so there is no module list to maintain.

```python
OrderServiceDep = Annotated[OrderService, Depends(Provide[Container.order_service])]

@router.post("", status_code=201, response_model=Envelope[OrderResponse])
@inject
async def create_order(body: OrderCreateRequest, service: OrderServiceDep):
    return success(await service.create(**body.model_dump()), message="Order created")
```

**Tests** swap anything: `app.container.order_repository.override(FakeOrderRepository())`.
Core tests skip the container entirely and pass fakes to the constructor (see
`tests/unit/core/`).

## 5. Data flow

```
schema (pydantic) → router → core service → repository interface
                                               ↓
                     Sql<Entity>Repository → ORM model → DB
                                               ↓
                    TypedDict ← _to_dict(row) ← row
```

- Repositories **return dicts** (typed as TypedDicts in `domain/entities/`), never ORM objects.
  Every repository has a `_to_dict(row)` mapper.
- Response schemas filter the dict on the way out (`response_model=Envelope[...]`), so internal
  fields (e.g. `hashed_password` on `UserWithPassword`) never leak.
- `Model` sets `eager_defaults`, so server-generated values (timestamps) are available right
  after `flush()` without an extra query.

## 6. Transactions

- **Core owns the transaction**: `async with self._uow(): ...`.
- Inside the block, every repository call shares one session (held in a context variable).
  It commits once at the end and rolls back on any exception. Nested blocks join the outer one.
- Outside a block, each repository call opens a short-lived session that commits on its own:
  fine for single reads and single writes.
- Repositories never commit. Routers never open transactions.

```python
async with self._uow():
    order = await self._orders.create(...)
    await self._stock.reserve(order["product_id"], order["quantity"])
```

## 7. Infrastructure services and caching

`infrastructure/services/` holds technical services (`JwtTokenService`, `Argon2PasswordHasher`,
storage, email). They may combine anything. Core reaches one only through an interface in
`domain/interfaces/services.py`. Add an interface only when core needs to call the thing.

Caching:

1. **Cached repository (default).** `CachedOrderRepository(inner, cache)` implements the same
   interface and wraps the SQL one. On or off is a container change; core never knows.
2. **Cache port.** When caching is a business decision (idempotency keys, OTPs), core depends on
   a `CacheInterface` and infrastructure provides `RedisCache`.

## 8. Errors, responses, logging

Raise typed errors from `domain/exceptions.py` with an `ErrorCode`. The domain knows nothing
about HTTP; `api/exception_handlers.py` maps classes to statuses:

| Exception | Status |
|---|---|
| `BusinessRuleError` | 400 |
| `AuthenticationError` | 401 |
| `PermissionDeniedError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |
| request validation | 422 |
| `RateLimitedError` | 429 |
| `ServiceUnavailableError` | 503 |
| anything else | 500 (real message only when `DEBUG`) |

Every response uses one envelope (`shared/responses.py`); `DELETE` returns `204` with no body:

```json
{ "status": "success|error", "code": "OK", "message": "...", "data": {}, "errors": null, "meta": null }
```

Logging is structured: JSON lines (`LOG_FORMAT=json`) or readable console output. The
request-context middleware sets `request_id` (echoed as `X-Request-ID`), and auth binds
`user_id`, so every log line carries both. Sensitive keys are redacted. Add fields with
`extra=`:

```python
logger.info("Order created", extra={"event": "order.created", "order_id": str(order["id"])})
```

## 9. Configuration

`APP_ENV` (`development` | `staging` | `production` | `test`) selects the settings class.
Precedence: environment variables, then `.env`, then class defaults. Environment classes
only change defaults; every setting is declared in `base.py`. `get_settings()` is called by
the container, `main.py` and `manage.py`, nowhere else. The `test` settings ignore `.env`
and use in-memory SQLite.

## 10. Adding a domain

```bash
python manage.py startapp purchase_orders          # --entity to override the singular
```

This creates the schemas, router, core service, entity, repository interface, model,
repository and a core unit test. It registers the container providers, the `*ServiceDep`
alias, the router and a `<ENTITY>_NOT_FOUND` code at the `# [kit:...]` markers, and the
model is picked up by Alembic automatically. The generated domain is a working CRUD with a
single `name` column. Then:

1. Shape the model, entity, schemas and repository to the real fields.
2. `python manage.py makemigrations "add purchase orders"`, read it, `python manage.py migrate`.
3. Put the business rules in `core/purchase_orders.py`.

## 11. The short version

1. Routers parse and respond. Core decides. Repositories query. Infrastructure talks to the outside.
2. Core depends on interfaces, never implementations.
3. Everything is built in the container and injected.
4. Repositories return TypedDicts, never ORM objects.
5. Core owns transactions.
6. Raise typed errors; handlers produce responses.
7. `python manage.py lint` must pass.
