# Agent rules

Read `docs/ARCHITECTURE.md` before changing structure. Non-negotiable:

- Layers: `api` → `core` → `domain` ← `infrastructure`. Core and domain never import
  `infrastructure`, `api` or `config`. `python manage.py lint` must pass.
- New domain: `python manage.py startapp <name>`. Do not hand-create the layer files.
- Build objects only in `src/config/container.py`. Never instantiate a dependency inside a class,
  never call `get_settings()` outside container/main/manage, never call the container from core.
- Core takes `Protocol` interfaces from `src/domain/interfaces/`. Add an interface only when core
  needs the dependency.
- Repositories return TypedDicts via `_to_dict`, never ORM objects, and never commit.
- Transactions: `async with self._uow():` in core only.
- Errors: raise `src/domain/exceptions.py` classes with an `ErrorCode`; add codes to
  `src/shared/errors/codes.py`. Never build error responses in routers.
- Responses: `success()` / `paginated()` with `response_model=Envelope[...]`.
- Logging: `get_logger(__name__)`, `extra={"event": "<domain>.<action>", ...}`. No secrets.
- Keep the `# [kit:...]` marker comments; startapp inserts above them.
- Every model change ships with a migration (`makemigrations`), read before committing.
- Core changes come with unit tests using fakes (see `tests/unit/core/`).
