"""Operational commands.

    python -m app.cli migrate          # upgrade the schema to the latest migration + seed defaults
    python -m app.cli seed             # load demo data into an EMPTY database (test/staging)
    python -m app.cli seed --reset     # WIPE the database, then load demo data
    python -m app.cli seed-venues      # add the venue demo data to an already-seeded demo database
    python -m app.cli backup-offsite   # encrypt + copy the newest DB dump and KYC files off the server now
    python -m app.cli decrypt-backup IN OUT   # decrypt an off-server backup (needs BACKUP_PASSPHRASE)
    python -m app.cli prune-uploads [--dry-run]   # delete public uploads nothing refers to
    python -m app.cli move-uploads-to-s3     # copy local uploads to the bucket and rewrite links

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
    if args == ["seed-venues"]:
        from app.demo_data import SeedRefused
        from app.demo_marketplace import run_venues_only
        try:
            asyncio.run(run_venues_only())
        except SeedRefused as e:
            print(e)
            return 1
        return 0
    if args == ["backup-offsite"]:
        from app.services.storage_jobs import run_offsite_backup_sync
        print(run_offsite_backup_sync())
        return 0
    if len(args) == 3 and args[0] == "decrypt-backup":
        import os
        from pathlib import Path
        from app.services.storage_jobs import decrypt_file
        passphrase = os.environ.get("BACKUP_PASSPHRASE") or __import__("getpass").getpass("Backup passphrase: ")
        decrypt_file(Path(args[1]), Path(args[2]), passphrase)
        print(f"Decrypted to {args[2]}")
        return 0
    if args and args[0] == "prune-uploads" and set(args[1:]) <= {"--dry-run"}:
        from app.database import AsyncSessionLocal
        from app.services.storage_jobs import prune_orphan_uploads

        async def _prune():
            async with AsyncSessionLocal() as db:
                return await prune_orphan_uploads(db, dry_run="--dry-run" in args)
        print(asyncio.run(_prune()))
        return 0
    if args == ["move-uploads-to-s3"]:
        from app.services.storage_migrate import move_uploads_to_s3
        print(asyncio.run(move_uploads_to_s3()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
