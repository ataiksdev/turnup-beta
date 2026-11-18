"""Operational commands.

    python -m app.cli migrate   # upgrade the schema to the latest migration + seed defaults

docker-compose runs `migrate` once before the API and worker start, so several API
replicas never race each other running migrations at boot."""
import asyncio
import sys

from app.database import init_db


def main(argv: list[str]) -> int:
    if argv[1:] == ["migrate"]:
        asyncio.run(init_db())
        print("Database is up to date.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
