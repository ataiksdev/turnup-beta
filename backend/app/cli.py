"""Operational commands.

    python -m app.cli migrate          # upgrade the schema to the latest migration + seed defaults
    python -m app.cli seed             # load demo data into an EMPTY database (test/staging)
    python -m app.cli seed --reset     # WIPE the database, then load demo data

docker-compose runs `migrate` once before the API and worker start, so several API
replicas never race each other running migrations at boot. In Docker, seed with:
    docker compose run --rm migrate python -m app.cli seed
"""
import asyncio
import sys

from app.database import init_db


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args == ["migrate"]:
        asyncio.run(init_db())
        print("Database is up to date.")
        return 0
    if args and args[0] == "seed" and set(args[1:]) <= {"--reset"}:
        from app.config import settings
        from app.demo_data import SeedRefused, run

        if not settings.debug and "--reset" in args:
            print("Refusing to --reset with DEBUG=false: that looks like a production database.\n"
                  "Seed demo data only on test/staging (set DEBUG=true there).")
            return 1
        try:
            asyncio.run(run(reset="--reset" in args))
        except SeedRefused as e:
            print(e)
            return 1
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
