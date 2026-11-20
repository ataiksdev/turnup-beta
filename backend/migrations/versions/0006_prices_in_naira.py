"""prices in naira only

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-20 15:30:00

The first versions stored new events (and ticket types) with currency USD by default. Payments
are only ever taken in naira, so those labels were wrong and showed prices as "$3.5k".
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE events SET currency = 'NGN' WHERE currency IS NULL OR currency <> 'NGN'")
    op.execute("UPDATE ticket_tiers SET currency = 'NGN' WHERE currency IS NULL OR currency <> 'NGN'")


def downgrade() -> None:
    pass  # the old (wrong) labels aren't kept
