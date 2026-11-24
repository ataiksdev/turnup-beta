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
    """A database from before migrations existed (baseline schema, no alembic_version table)
    is stamped at the baseline and upgraded through every later migration."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}"
    assert _alembic("upgrade", "0001", url=url).returncode == 0
    drop_version = _run([sys.executable, "-c", (
        "import asyncio, sqlalchemy as sa\n"
        "from app.database import engine\n"
        "async def main():\n"
        "    async with engine.begin() as c:\n"
        "        await c.execute(sa.text('DROP TABLE alembic_version'))\n"
        "asyncio.run(main())\n"
    )], url)
    assert drop_version.returncode == 0, drop_version.stderr

    r = _run([sys.executable, "-c",
              "import asyncio; from app.database import init_db; asyncio.run(init_db())"], url)
    assert r.returncode == 0, r.stderr
    assert "(head)" in _alembic("current", url=url).stdout
    assert _alembic("check", url=url).returncode == 0


# Seeds rows into a database held at an OLD revision. The models describe the newest schema,
# so inserting through them breaks whenever a later migration adds a column. This inserts only
# the columns the old table has, filling the models' Python-side defaults for the rest.
OLD_SCHEMA_INSERT = (
    "import sqlalchemy as sa\n"
    "import app.main  # noqa: F401  (registers every model)\n"
    "from app.database import Base, engine\n"
    "async def insert(table, **values):\n"
    "    async with engine.begin() as c:\n"
    "        have = {col['name'] for col in await c.run_sync(lambda s: sa.inspect(s).get_columns(table))}\n"
    "        row = {}\n"
    "        for col in Base.metadata.tables[table].columns:\n"
    "            if col.name not in have:\n"
    "                continue\n"
    "            if col.name in values:\n"
    "                row[col.name] = values[col.name]\n"
    "            elif col.default is not None:\n"
    "                arg = col.default.arg\n"
    "                row[col.name] = arg(None) if callable(arg) else arg\n"
    "        await c.execute(sa.insert(sa.table(table, *map(sa.column, row))).values(**row))\n"
)


def test_retired_themes_move_to_the_default(db_url):
    """Migration 0005: Lagoon, Palm and Neon Night were removed; people on them get the
    default theme with their light/dark/system choice kept."""
    assert _alembic("upgrade", "0004", url=db_url).returncode == 0
    seed = _run([sys.executable, "-c", OLD_SCHEMA_INSERT + (
        "import asyncio, uuid\n"
        "async def main():\n"
        "    for name, pref in [('m_neon', 'neon:light'), ('m_palm', 'palm:system'),\n"
        "                       ('m_lagoon', 'lagoon:dark'), ('m_gold', 'gold:dark'), ('m_none', None)]:\n"
        "        await insert('users', id=str(uuid.uuid4()), username=name, email=f'{name}@example.com',\n"
        "                     full_name=name, theme_preference=pref)\n"
        "asyncio.run(main())\n"
    )], db_url)
    assert seed.returncode == 0, seed.stderr
    assert _alembic("upgrade", "head", url=db_url).returncode == 0
    read = _run([sys.executable, "-c", (
        "import asyncio, sqlalchemy as sa\n"
        "from app.database import engine\n"
        "async def main():\n"
        "    async with engine.connect() as c:\n"
        "        rows = (await c.execute(sa.text(\"SELECT username, theme_preference FROM users \"\n"
        "                                         \"WHERE username LIKE 'm\\\\_%' ESCAPE '\\\\' ORDER BY username\"))).all()\n"
        "        print(dict(rows))\n"
        "asyncio.run(main())\n"
    )], db_url)
    assert read.returncode == 0, read.stderr
    assert eval(read.stdout.strip().splitlines()[-1]) == {
        "m_gold": "gold:dark", "m_lagoon": "turnup:dark", "m_neon": "turnup:light",
        "m_none": None, "m_palm": "turnup:system"}


def test_old_usd_prices_become_naira(db_url):
    """Migration 0006: events and ticket types stored as USD (the first versions' default) are
    relabelled NGN, the only currency payments are taken in."""
    assert _alembic("upgrade", "0005", url=db_url).returncode == 0
    seed = _run([sys.executable, "-c", OLD_SCHEMA_INSERT + (
        "import asyncio, uuid\n"
        "from datetime import datetime, timedelta, timezone\n"
        "async def main():\n"
        "    uid = str(uuid.uuid4()); now = datetime.now(timezone.utc)\n"
        "    await insert('users', id=uid, username='usd_host', email='usd@example.com', full_name='Host')\n"
        "    await insert('events', id='ev-usd', slug='ev-usd', title='Old Party', description='d'*30, venue_name='Hall',\n"
        "                 address='1 Street', city='Lagos', country='NG', start_date=now, end_date=now + timedelta(hours=2),\n"
        "                 host_id=uid, status='published', currency='USD')\n"
        "    await insert('ticket_tiers', id='tier-usd', event_id='ev-usd', name='Regular', price=3500, currency='USD')\n"
        "asyncio.run(main())\n"
    )], db_url)
    assert seed.returncode == 0, seed.stderr
    assert _alembic("upgrade", "head", url=db_url).returncode == 0
    read = _run([sys.executable, "-c", (
        "import asyncio, sqlalchemy as sa\n"
        "from app.database import engine\n"
        "async def main():\n"
        "    async with engine.connect() as c:\n"
        "        e = (await c.execute(sa.text(\"SELECT currency FROM events WHERE id='ev-usd'\"))).scalar()\n"
        "        t = (await c.execute(sa.text(\"SELECT currency FROM ticket_tiers WHERE id='tier-usd'\"))).scalar()\n"
        "        print(e, t)\n"
        "asyncio.run(main())\n"
    )], db_url)
    assert read.returncode == 0, read.stderr
    assert read.stdout.strip().splitlines()[-1] == "NGN NGN"


def test_api_stores_prices_in_naira_whatever_is_sent():
    from app.schemas.event import EventCreate
    from app.schemas.organizer import TicketTierCreate
    assert TicketTierCreate(name="VIP", price=5000, currency="USD").currency == "NGN"
    assert EventCreate.model_fields["currency"].default == "NGN"


_SEED_ORDERS = OLD_SCHEMA_INSERT + (
    "import asyncio, uuid\n"
    "from datetime import datetime, timedelta, timezone\n"
    "async def main():\n"
    "    uid = str(uuid.uuid4()); now = datetime.now(timezone.utc)\n"
    "    await insert('users', id=uid, username='code_host', email='code@example.com', full_name='Host')\n"
    "    await insert('events', id='ev-code', slug='ev-code', title='Party', description='d'*30, venue_name='Hall',\n"
    "                 address='1 Street', city='Lagos', country='NG', start_date=now, end_date=now + timedelta(hours=2),\n"
    "                 host_id=uid, status='published')\n"
    "    await insert('ticket_tiers', id='tier-code', event_id='ev-code', name='Regular', price=0)\n"
    "    for oid, status in (('order-confirmed', 'confirmed'), ('order-pending', 'pending')):\n"
    "        await insert('ticket_orders', id=oid, user_id=uid, event_id='ev-code', tier_id='tier-code', quantity=1,\n"
    "                     unit_price=0, total_price=0, status=status)\n"
    "asyncio.run(main())\n"
)

_DROP_TICKET_CODE = (
    "import asyncio, sqlalchemy as sa\n"
    "from app.database import engine\n"
    "async def main():\n"
    "    async with engine.begin() as c:\n"
    "        await c.execute(sa.text('DROP INDEX IF EXISTS ix_ticket_orders_ticket_code'))\n"
    "        await c.execute(sa.text('ALTER TABLE ticket_orders DROP COLUMN ticket_code'))\n"
    "asyncio.run(main())\n"
)

_READ_TICKET_CODES = (
    "import asyncio, sqlalchemy as sa\n"
    "from app.database import engine\n"
    "async def main():\n"
    "    async with engine.connect() as c:\n"
    "        rows = dict((await c.execute(sa.text('SELECT id, ticket_code FROM ticket_orders'))).all())\n"
    "        idx = await c.run_sync(lambda s: [i for i in sa.inspect(s).get_indexes('ticket_orders')\n"
    "                                          if i['column_names'] == ['ticket_code']])\n"
    "        print(repr({'confirmed': rows.get('order-confirmed'), 'pending': rows.get('order-pending'),\n"
    "                    'unique_index': any(i['unique'] for i in idx)}))\n"
    "asyncio.run(main())\n"
)


def test_missing_ticket_code_is_repaired(db_url):
    """Migration 0007: a database stamped as up to date but missing ticket_orders.ticket_code (an
    old SQLite database upgraded by the old code) gets the column, its unique index, and codes
    for confirmed tickets. Listing tickets failed with 'no such column' before."""
    assert _alembic("upgrade", "0006", url=db_url).returncode == 0
    for script in (_SEED_ORDERS, _DROP_TICKET_CODE):
        r = _run([sys.executable, "-c", script], db_url)
        assert r.returncode == 0, r.stderr
    up = _alembic("upgrade", "head", url=db_url)
    assert up.returncode == 0, up.stderr
    read = _run([sys.executable, "-c", _READ_TICKET_CODES], db_url)
    assert read.returncode == 0, read.stderr
    state = eval(read.stdout.strip().splitlines()[-1])
    assert len(state["confirmed"] or "") == 36 and state["pending"] is None and state["unique_index"], state
    # And the schema now matches the models again.
    check = _alembic("check", url=db_url)
    assert check.returncode == 0, check.stdout + check.stderr


def test_legacy_sqlite_database_gets_ticket_code(tmp_path):
    """The upgrade path for databases from before migrations: SQLite can't ADD a UNIQUE column, which
    used to be swallowed so the column was never added. Now it's added with a separate unique index."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'legacy-codes.db'}"
    assert _alembic("upgrade", "0001", url=url).returncode == 0
    for script in (_DROP_TICKET_CODE, (
        "import asyncio, sqlalchemy as sa\n"
        "from app.database import engine\n"
        "async def main():\n"
        "    async with engine.begin() as c:\n"
        "        await c.execute(sa.text('DROP TABLE alembic_version'))\n"
        "asyncio.run(main())\n")):
        r = _run([sys.executable, "-c", script], url)
        assert r.returncode == 0, r.stderr
    r = _run([sys.executable, "-c",
              "import asyncio; from app.database import init_db; asyncio.run(init_db())"], url)
    assert r.returncode == 0, r.stderr
    read = _run([sys.executable, "-c", _READ_TICKET_CODES], url)
    assert read.returncode == 0, read.stderr
    assert eval(read.stdout.strip().splitlines()[-1])["unique_index"] is True
    assert _alembic("check", url=url).returncode == 0
