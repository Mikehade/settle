# Extras

Not included by default. Each follows the same pattern: implementation in `infrastructure/`,
an interface in `domain/interfaces/` **only if core calls it**, wiring in the container, async
teardown in `main.py`'s lifespan.

## Redis (cache)

`uv add redis`, then add `REDIS_URL: str` to `config/base.py`.

```python
# src/domain/interfaces/services.py
class CacheInterface(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...

# src/infrastructure/cache/redis_cache.py
class RedisCache:
    name = "redis"

    def __init__(self, url: str) -> None:
        self._client = redis.asyncio.from_url(url, decode_responses=True)

    async def get(self, key): return await self._client.get(key)
    async def set(self, key, value, ttl_seconds=None): await self._client.set(key, value, ex=ttl_seconds)
    async def delete(self, key): await self._client.delete(key)
    async def ping(self) -> bool: return await self._client.ping()
    async def close(self) -> None: await self._client.aclose()
```

```python
# container.py  (# ---- Resources)
cache = providers.Singleton(RedisCache, url=config.provided.REDIS_URL)
health_service = providers.Singleton(HealthService, checks=providers.List(database, cache))

# main.py lifespan, after yield
await container.cache().close()
```

Caching a repository without touching core:

```python
# src/infrastructure/repositories/cached_orders.py
class CachedOrderRepository:
    def __init__(self, inner: SqlOrderRepository, cache: RedisCache, ttl_seconds: int = 300): ...
    async def get(self, order_id):        # read-through; other methods delegate and invalidate
        ...

# container.py
sql_order_repository = providers.Singleton(SqlOrderRepository, db=database)
order_repository = providers.Singleton(CachedOrderRepository, inner=sql_order_repository, cache=cache)
```

Rate limiting: a pure ASGI middleware in `api/middleware/` that gets the cache through
`app.container` (not an import from infrastructure), so the layer contract holds.

## Background jobs (Celery / arq / Dramatiq)

- App and broker config: `infrastructure/tasks/app.py`.
- Task functions: `infrastructure/tasks/<domain>.py`. A task is an entry point like a router:
  it builds a `Container()`, calls a core service, disposes resources. No business logic in tasks.
- Enqueueing from core goes through an interface (`TaskQueueInterface.enqueue(name, payload)`)
  implemented in infrastructure.

## Object storage (S3 / GCS)

`StorageInterface` (`upload`, `signed_url`, `delete`) in `domain/interfaces/services.py`,
`S3Storage` / `GCSStorage` in `infrastructure/services/storage.py`, credentials from settings.

## Email / external HTTP APIs

Same shape: `EmailSenderInterface` + `SmtpEmailSender` / `SendgridEmailSender`. HTTP clients:
one shared `httpx.AsyncClient` Singleton in the container, closed in lifespan, injected into
the client classes in `infrastructure/services/`.

## Second database

A second `Database` provider (`analytics_db = providers.Singleton(Database, url=...)`) and its
own repositories bound to it. A repository receives exactly one `Database`, so it cannot reach
the other one by accident. Alembic manages only the database this service owns.

## Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
ENV APP_ENV=production PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
```

Run migrations as a separate release step (`python manage.py migrate`), not on app start.
