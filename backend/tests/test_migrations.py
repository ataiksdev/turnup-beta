"""Alembic migrations must build exactly the schema the models describe, so a model change
without a matching migration fails CI instead of failing in production.

Runs against TEST_DATABASE_URL when it points at Postgres (CI), else a temporary SQLite file.
Uses subprocesses because the app's engine and Alembic's env.py read DATABASE_URL at import.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


def _run(args: list[str], url: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": url, "DEBUG": "true"}
    return subprocess.run(args, cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)


def _alembic(*args: str, url: str) -> subprocess.CompletedProcess:
    return _run([sys.executable, "-m", "alembic", *args], url)


@pytest.fixture
def db_url(tmp_path):
    pg = os.environ.get("TEST_DATABASE_URL", "")
    if pg.startswith("postgresql"):
        # A separate database from the one the rest of the suite uses (CI creates it).
        url = pg.rsplit("/", 1)[0] + "/turnup_migrations"
        _alembic("downgrade", "base", url=url)
        yield url
        _alembic("downgrade", "base", url=url)
    else:
        yield f"sqlite+aiosqlite:///{tmp_path / 'migrations.db'}"


def test_migrations_match_models(db_url):
    up = _alembic("upgrade", "head", url=db_url)
    assert up.returncode == 0, up.stderr
    check = _alembic("check", url=db_url)
    assert check.returncode == 0, (
        "Models and migrations differ. Generate a migration with:\n"
        "  alembic revision --autogenerate -m '<what changed>'\n\n" + check.stdout + check.stderr
    )


def test_migrations_downgrade_cleanly(db_url):
    assert _alembic("upgrade", "head", url=db_url).returncode == 0
    down = _alembic("downgrade", "base", url=db_url)
    assert down.returncode == 0, down.stderr


def test_app_startup_initialises_a_fresh_database(db_url):
    r = _run([sys.executable, "-c",
              "import asyncio; from app.database import init_db; asyncio.run(init_db())"], db_url)
    assert r.returncode == 0, r.stderr
    current = _alembic("current", url=db_url)
    assert "(head)" in current.stdout


def test_pre_alembic_database_is_adopted(tmp_path):
    """A database built the old way (create_all, no alembic_version) is patched, stamped at
    the baseline and upgraded, ending up identical to a migrated one."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}"
    make_legacy = _run([sys.executable, "-c", (
        "import asyncio\n"
        "from app.database import Base, engine\n"
        "import app.models.user, app.models.event, app.models.social, app.models.auth_tokens\n"
        "import app.models.organizer, app.models.community, app.models.scout, app.models.settings\n"
        "async def main():\n"
        "    async with engine.begin() as c:\n"
        "        await c.run_sync(Base.metadata.create_all)\n"
        "asyncio.run(main())\n"
    )], url)
    assert make_legacy.returncode == 0, make_legacy.stderr

    r = _run([sys.executable, "-c",
              "import asyncio; from app.database import init_db; asyncio.run(init_db())"], url)
    assert r.returncode == 0, r.stderr
    assert "(head)" in _alembic("current", url=url).stdout
    assert _alembic("check", url=url).returncode == 0
