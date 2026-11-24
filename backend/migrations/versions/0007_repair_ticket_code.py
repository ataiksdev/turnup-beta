"""repair ticket_orders.ticket_code on databases that never got it

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-24 10:00:00

Databases created before migrations existed were upgraded by app/database.py with
"ALTER TABLE ticket_orders ADD COLUMN ticket_code VARCHAR(36) UNIQUE". SQLite can't add a UNIQUE
column, the error was taken for "already exists", and the database was stamped as up to date
without the column, so listing or opening tickets failed ("no such column:
ticket_orders.ticket_code"). This adds the column and its unique index where they're missing,
and gives confirmed tickets that have no code one, so their QR codes work. Databases that already
have them are left alone.
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "ix_ticket_orders_ticket_code"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = {c["name"] for c in insp.get_columns("ticket_orders")}
    if "ticket_code" not in columns:
        op.add_column("ticket_orders", sa.Column("ticket_code", sa.String(length=36), nullable=True))
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("ticket_orders")}
    unique_constraints = {u["name"] for u in sa.inspect(bind).get_unique_constraints("ticket_orders")}
    # Postgres databases from the old upgrade code carry a UNIQUE constraint instead: also fine.
    has_unique = INDEX in indexes or any("ticket_code" in (n or "") for n in unique_constraints)
    if not has_unique:
        op.create_index(INDEX, "ticket_orders", ["ticket_code"], unique=True)

    # Confirmed tickets without a code (e.g. bought while the column was missing elsewhere).
    orders = sa.table("ticket_orders", sa.column("id", sa.String), sa.column("status", sa.String),
                      sa.column("ticket_code", sa.String))
    missing = bind.execute(sa.select(orders.c.id).where(
        orders.c.status == "confirmed", orders.c.ticket_code.is_(None))).scalars().all()
    for order_id in missing:
        bind.execute(orders.update().where(orders.c.id == order_id).values(ticket_code=str(uuid.uuid4())))


def downgrade() -> None:
    pass  # a repair: there's nothing to undo on a healthy database
