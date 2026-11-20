"""retire the Lagoon, Palm and Neon Night themes

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20 10:00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RETIRED = ("lagoon", "palm", "neon")


def upgrade() -> None:
    # People on a removed theme move to the default theme and keep their light/dark/system choice.
    for theme in RETIRED:
        op.execute(
            f"UPDATE users SET theme_preference = 'turnup' || substr(theme_preference, {len(theme) + 1}) "
            f"WHERE theme_preference LIKE '{theme}:%'"
        )


def downgrade() -> None:
    pass  # the old choice isn't kept; Turnup stays valid either way
