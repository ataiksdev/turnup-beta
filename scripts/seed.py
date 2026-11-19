#!/usr/bin/env python3
"""Load demo data (kept for the old command; the seeder lives in backend/app/demo_data.py).

    python scripts/seed.py            # same as: cd backend && python -m app.cli seed
    python scripts/seed.py --reset    # wipe the database first
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["app.cli", "seed", *sys.argv[1:]]))
