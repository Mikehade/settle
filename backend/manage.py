#!/usr/bin/env python
"""Project CLI.

    python manage.py --help
"""
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

cli = typer.Typer(no_args_is_help=True, add_completion=False, help="Project management commands.")


def _alembic_config():
    from alembic.config import Config

    return Config(str(ROOT / "alembic.ini"))


def _fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


# ---- Server ----------------------------------------------------------------
@cli.command()
def runserver(
    host: str = typer.Option(None, help="Defaults to settings.HOST"),
    port: int = typer.Option(None, help="Defaults to settings.PORT"),
    reload: bool = typer.Option(None, help="Defaults to on in development"),
) -> None:
    """Run the development server (uvicorn)."""
    import uvicorn

    from src.config import get_settings

    s = get_settings()
    uvicorn.run(
        "main:app",
        host=host or s.HOST,
        port=port or s.PORT,
        reload=s.APP_ENV == "development" if reload is None else reload,
        log_config=None,
    )


# ---- Scaffolding -----------------------------------------------------------
@cli.command()
def startapp(
    name: str = typer.Argument(..., help="Domain name, plural snake_case: orders, purchase_orders"),
    entity: str = typer.Option(None, help="Singular entity name if the guess is wrong: --entity person"),
) -> None:
    """Create every layer for a new domain and register it."""
    from scripts.scaffold import startapp as run_startapp

    try:
        created = run_startapp(name, entity)
    except (ValueError, FileExistsError) as exc:
        _fail(str(exc))
    # Sort imports in the new files (template import order depends on the domain name).
    if shutil.which("ruff"):
        subprocess.run(["ruff", "check", "--fix", "--select", "I", "--quiet", *created], cwd=ROOT, check=False)
    for path in created:
        typer.echo(f"  created  {path}")
    typer.echo("  updated  container.py, api/deps.py, api/router.py, shared/errors/codes.py")
    typer.secho(f"\nNext: edit the model, then `python manage.py makemigrations \"add {name}\"`.", fg=typer.colors.GREEN)


# ---- Migrations ------------------------------------------------------------
@cli.command()
def makemigrations(message: str = typer.Argument(..., help="Short description")) -> None:
    """Autogenerate a migration from model changes. Read it before committing."""
    from alembic import command

    command.revision(_alembic_config(), message=message, autogenerate=True)


@cli.command()
def migrate(revision: str = typer.Argument("head")) -> None:
    """Apply migrations up to REVISION (default: head)."""
    from alembic import command

    command.upgrade(_alembic_config(), revision)


@cli.command()
def revert(revision: str = typer.Argument("-1")) -> None:
    """Revert migrations down to REVISION (default: one step)."""
    from alembic import command

    command.downgrade(_alembic_config(), revision)


@cli.command()
def history() -> None:
    """Show migration history."""
    from alembic import command

    command.history(_alembic_config(), verbose=False)


@cli.command()
def current() -> None:
    """Show the revision the database is at."""
    from alembic import command

    command.current(_alembic_config(), verbose=False)


@cli.command()
def stamp(revision: str = typer.Argument("head")) -> None:
    """Mark the database as being at REVISION without running migrations."""
    from alembic import command

    command.stamp(_alembic_config(), revision)


# ---- Users -----------------------------------------------------------------
@cli.command()
def createsuperuser(
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True, envvar="SUPERUSER_PASSWORD"),
    full_name: str = typer.Option(None),
) -> None:
    """Create a superuser through UserService (same rules as the API)."""
    from src.domain.exceptions import AppError

    async def _run() -> dict:
        container = _container()
        try:
            return await container.user_service().create_user(
                email=email, password=password, full_name=full_name, is_superuser=True
            )
        finally:
            await container.database().dispose()

    try:
        user = asyncio.run(_run())
    except AppError as exc:
        _fail(f"{exc.code}: {exc.message}")
    typer.secho(f"Superuser {user['email']} created.", fg=typer.colors.GREEN)


@cli.command()
def changepassword(
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt="New password", hide_input=True, confirmation_prompt=True),
) -> None:
    """Change a user's password."""
    from src.domain.exceptions import AppError

    async def _run() -> None:
        container = _container()
        try:
            await container.user_service().change_password(email=email, new_password=password)
        finally:
            await container.database().dispose()

    try:
        asyncio.run(_run())
    except AppError as exc:
        _fail(f"{exc.code}: {exc.message}")
    typer.secho("Password changed.", fg=typer.colors.GREEN)


# ---- Utilities -------------------------------------------------------------
def _container():
    from src.config import get_settings
    from src.config.container import Container
    from src.shared.logging import configure_logging

    s = get_settings()
    configure_logging(level="WARNING", fmt="console", service=s.APP_NAME, env=s.APP_ENV)
    return Container()


@cli.command()
def shell() -> None:
    """Interactive shell with `container` and `settings` loaded. Use asyncio.run(...) for coroutines."""
    import code

    container = _container()
    namespace = {"container": container, "settings": container.config(), "asyncio": asyncio}
    banner = "Loaded: container, settings, asyncio"
    try:
        from IPython import start_ipython

        start_ipython(argv=[], user_ns=namespace)
    except ImportError:
        code.interact(banner=banner, local=namespace)


@cli.command()
def routes() -> None:
    """List every route (from the OpenAPI schema, so included routers are covered)."""
    from main import app

    for path, operations in app.openapi()["paths"].items():
        for method, op in operations.items():
            typer.echo(f"{method.upper():<8} {path:<50} {op.get('summary', '')}")


@cli.command()
def check() -> None:
    """Check settings, app wiring, database connectivity and pending migrations."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    from src.config import get_settings

    s = get_settings()
    typer.echo(f"settings    ok  ({type(s).__name__}, APP_ENV={s.APP_ENV})")

    import main  # noqa: F401  builds the app and wires the container

    typer.echo("app         ok")

    db = _container().database()

    async def _db() -> set[str]:
        try:
            async with db.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                return set(await conn.run_sync(lambda c: MigrationContext.configure(c).get_current_heads()))
        finally:
            await db.dispose()

    try:
        current_heads = asyncio.run(_db())
    except Exception as exc:  # noqa: BLE001
        _fail(f"database    FAILED  {type(exc).__name__}: {exc}")
    typer.echo("database    ok")

    heads = set(ScriptDirectory.from_config(_alembic_config()).get_heads())
    if heads == current_heads:
        typer.echo("migrations  ok  (up to date)")
    else:
        typer.secho(f"migrations  PENDING  (db: {sorted(current_heads) or 'none'}, code: {sorted(heads) or 'none'})", fg=typer.colors.YELLOW)


@cli.command()
def seed() -> None:
    """Load development data (scripts/seed.py)."""
    from scripts.seed import run

    async def _run() -> None:
        container = _container()
        try:
            await run(container)
        finally:
            await container.database().dispose()

    asyncio.run(_run())


@cli.command()
def lint() -> None:
    """ruff + import-linter (layer rules)."""
    failed = False
    for cmd in (["ruff", "check", "."], ["lint-imports"]):
        typer.secho("$ " + " ".join(cmd), bold=True)
        failed |= subprocess.run(cmd, cwd=ROOT).returncode != 0
    if failed:
        raise typer.Exit(1)


@cli.command("export-reqs")
def export_reqs() -> None:
    """Regenerate requirements.txt / requirements-dev.txt from uv.lock (pinned)."""
    base = ["uv", "export", "--no-hashes", "--no-emit-project", "--quiet"]
    subprocess.run([*base, "--no-dev", "-o", "requirements.txt"], cwd=ROOT, check=True)
    subprocess.run([*base, "-o", "requirements-dev.txt"], cwd=ROOT, check=True)
    typer.echo("Wrote requirements.txt and requirements-dev.txt")


if __name__ == "__main__":
    cli()
