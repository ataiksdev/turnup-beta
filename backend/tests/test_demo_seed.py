"""The demo seeder: fills an empty database, refuses to mix into a used one, and --reset
works (it must wipe every table in foreign-key order, which also matters on Postgres)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


def _seed(url: str, *args: str, debug: str = "true") -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": url, "DEBUG": debug,
           "SECRET_KEY": "seed-test-secret-0123456789abcdef"}
    return subprocess.run([sys.executable, "-m", "app.cli", "seed", *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=300)


@pytest.fixture
def db_url(tmp_path):
    pg = os.environ.get("TEST_DATABASE_URL", "")
    if pg.startswith("postgresql"):
        yield pg.rsplit("/", 1)[0] + "/turnup_migrations"  # throwaway DB shared with test_migrations
    else:
        yield f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}"


def test_seed_fill_refuse_and_reset(db_url):
    first = _seed(db_url, "--reset")  # --reset: the DB may hold leftovers from other tests
    assert first.returncode == 0, first.stdout + first.stderr
    assert "Seed complete" in first.stdout
    for line in ("communities", "reviews", "waitlist", "approval queue", "organizer profiles"):
        assert line in first.stdout, f"missing section: {line}"

    again = _seed(db_url)
    assert again.returncode == 1 and "already has" in again.stdout  # never mixes into real data

    reset = _seed(db_url, "--reset")
    assert reset.returncode == 0, reset.stdout + reset.stderr


def test_reset_refused_outside_debug(db_url):
    r = _seed(db_url, "--reset", debug="false")
    assert r.returncode == 1 and "Refusing" in r.stdout
