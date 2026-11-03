"""`manage.py startapp` implementation: render domain templates and register the domain.

Registration inserts lines just above `# [kit:...]` markers. It is idempotent and refuses to
overwrite existing files.
"""
from __future__ import annotations

import keyword
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Path(__file__).resolve().parent / "templates" / "domain"
RESERVED = {"api", "core", "domain", "infrastructure", "config", "shared", "health", "auth", "common", "base", "deps"}


@dataclass(frozen=True)
class Names:
    domain: str   # orders            module / package name
    entity: str   # order             variable name
    Entity: str   # Order             class prefix
    ENTITY: str   # ORDER             error code prefix
    route: str    # orders            URL segment (kebab-case)
    title: str    # Orders            OpenAPI tag
    table: str    # orders            table name

    def tokens(self) -> dict[str, str]:
        return {
            "__domain__": self.domain,
            "__entity__": self.entity,
            "__Entity__": self.Entity,
            "__ENTITY__": self.ENTITY,
            "__route__": self.route,
            "__Title__": self.title,
            "__table__": self.table,
        }


def singularize(word: str) -> str:
    head, _, last = word.rpartition("_")
    if last.endswith("ies") and len(last) > 3:
        last = last[:-3] + "y"
    elif last.endswith(("sses", "xes", "ches", "shes", "zes")):
        last = last[:-2]
    elif last.endswith("s") and not last.endswith(("ss", "us", "is")):
        last = last[:-1]
    return f"{head}_{last}" if head else last


def build_names(raw: str, entity: str | None = None) -> Names:
    domain = re.sub(r"[-\s]+", "_", raw.strip()).lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", domain) or keyword.iskeyword(domain):
        raise ValueError(f"Invalid domain name {raw!r}: use snake_case, e.g. purchase_orders")
    if domain in RESERVED:
        raise ValueError(f"{domain!r} is reserved")
    entity_snake = re.sub(r"(?<!^)(?=[A-Z])", "_", entity).lower() if entity else singularize(domain)
    if entity_snake == domain + "s":
        raise ValueError("Entity name must not be the plural of the domain")
    pascal = "".join(p.capitalize() for p in entity_snake.split("_"))
    return Names(
        domain=domain,
        entity=entity_snake,
        Entity=pascal,
        ENTITY=entity_snake.upper(),
        route=domain.replace("_", "-"),
        title=" ".join(p.capitalize() for p in domain.split("_")),
        table=domain,
    )


def _render(text: str, names: Names) -> str:
    for key, value in names.tokens().items():
        text = text.replace(key, value)
    return text


def _insert_at_marker(path: Path, marker: str, snippet: str) -> bool:
    """Insert `snippet` above the line containing `marker`, matching its indentation."""
    text = path.read_text(encoding="utf-8")
    first_line = snippet.strip().splitlines()[0].strip()
    if any(line.strip() == first_line for line in text.splitlines()):
        return False
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if marker in line:
            indent = line[: len(line) - len(line.lstrip())]
            body = snippet.lstrip("\n").removesuffix("\n").split("\n")
            block = "".join(f"{indent}{s}\n" if s else "\n" for s in body)
            lines.insert(i, block)
            path.write_text("".join(lines), encoding="utf-8")
            return True
    raise RuntimeError(f"Marker {marker!r} not found in {path.relative_to(ROOT)}")


def startapp(raw: str, entity: str | None = None, root: Path = ROOT) -> list[str]:
    n = build_names(raw, entity)
    d = n.domain
    files = {
        "schemas.py.tpl": f"src/api/{d}/schemas.py",
        "router.py.tpl": f"src/api/{d}/router.py",
        "service.py.tpl": f"src/core/{d}.py",
        "entity.py.tpl": f"src/domain/entities/{d}.py",
        "repository_interface.py.tpl": f"src/domain/interfaces/repositories/{d}.py",
        "model.py.tpl": f"src/infrastructure/db/models/{d}.py",
        "repository.py.tpl": f"src/infrastructure/repositories/{d}.py",
        "test_service.py.tpl": f"tests/unit/core/test_{d}.py",
    }
    existing = [dst for dst in files.values() if (root / dst).exists()]
    if existing:
        raise FileExistsError("Already exists: " + ", ".join(existing))

    created: list[str] = []
    for template, dst in files.items():
        target = root / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render((TEMPLATES / template).read_text(encoding="utf-8"), n), encoding="utf-8")
        created.append(dst)
    init = root / f"src/api/{d}/__init__.py"
    init.touch()
    created.append(str(init.relative_to(root)))

    registrations = [
        ("src/config/container.py", "# [kit:imports]",
         f"from src.core.{d} import {n.Entity}Service\n"
         f"from src.infrastructure.repositories.{d} import Sql{n.Entity}Repository"),
        ("src/config/container.py", "# [kit:repositories]",
         f"{n.entity}_repository = providers.Singleton(Sql{n.Entity}Repository, db=database)"),
        ("src/config/container.py", "# [kit:core]",
         f"{n.entity}_service = providers.Singleton(\n"
         f"    {n.Entity}Service, {d}={n.entity}_repository, uow=uow.provider\n)"),
        ("src/api/deps.py", "# [kit:imports]", f"from src.core.{d} import {n.Entity}Service"),
        ("src/api/deps.py", "# [kit:deps]",
         f"{n.Entity}ServiceDep = Annotated[{n.Entity}Service, Depends(Provide[Container.{n.entity}_service])]"),
        ("src/api/router.py", "# [kit:router-imports]", f"from src.api.{d}.router import router as {d}_router"),
        ("src/api/router.py", "# [kit:routers]", f"api_router.include_router({d}_router)"),
        ("src/shared/errors/codes.py", "# [kit:codes]",
         f"# ---- {n.title} {'-' * max(3, 66 - len(n.title))}\n"
         f'{n.ENTITY}_NOT_FOUND = "{n.ENTITY}_NOT_FOUND"\n\n'),
    ]
    for path, marker, snippet in registrations:
        _insert_at_marker(root / path, marker, snippet)
    return created
