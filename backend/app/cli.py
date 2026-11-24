"""Operational commands.

    python -m app.cli migrate          # upgrade the schema to the latest migration + seed defaults
    python -m app.cli seed             # load demo data into an EMPTY database (test/staging)
    python -m app.cli seed --reset     # WIPE the database, then load demo data
    python -m app.cli seed-venues      # add the venue demo data to an already-seeded demo database
    python -m app.cli seed-activity [--users N] [--events N] [--days N]
                                       # synthetic people + weeks of app activity (DEBUG=true only)
    python -m app.cli recs-features    # recompute recommendation features now (the worker does this)
    python -m app.cli recs-eval [--holdout-days N] [--k N]   # offline ranker evaluation
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


def _int_opts(args: list[str], allowed: set[str]) -> dict[str, int]:
    """`--name 5` pairs -> {"--name": 5}."""
    if len(args) % 2 or any(a not in allowed for a in args[::2]):
        raise ValueError(f"Options: {', '.join(sorted(allowed))} followed by a number")
    return {k: int(v) for k, v in zip(args[::2], args[1::2])}


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
    if args and args[0] == "seed-activity":
        from app.demo_activity import run as seed_activity
        from app.demo_data import SeedRefused
        try:
            opts = _int_opts(args[1:], {"--users", "--events", "--days"})
        except ValueError as e:
            print(e)
            return 2
        try:
            print(asyncio.run(seed_activity(**{k[2:]: v for k, v in opts.items()})))
        except SeedRefused as e:
            print(e)
            return 1
        return 0
    if args == ["recs-features"]:
        import app.main  # noqa: F401  (registers every model)
        from app.database import AsyncSessionLocal
        from app.services.rec_features import run_event_features, run_user_features

        async def _features():
            async with AsyncSessionLocal() as db:
                return await run_event_features(db), await run_user_features(db)
        print(asyncio.run(_features()))
        return 0
    if args and args[0] == "recs-eval":
        import json
        import app.main  # noqa: F401  (registers every model)
        from app.database import AsyncSessionLocal
        from app.services.rec_eval import evaluate
        try:
            opts = _int_opts(args[1:], {"--holdout-days", "--k"})
        except ValueError as e:
            print(e)
            return 2

        async def _eval():
            async with AsyncSessionLocal() as db:
                return await evaluate(db, **{k[2:].replace("-", "_"): v for k, v in opts.items()})
        print(json.dumps(asyncio.run(_eval()), indent=2))
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
