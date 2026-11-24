"""activity tracking and recommendation features

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-24 17:44:41

The activity log (what people do in the app), the per-user and per-event numbers the
recommendations are computed from, and the user's data choices. See
docs/recommendations-spec.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('activity_log',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('client_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=40), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('anonymous_id', sa.String(length=64), nullable=True),
    sa.Column('session_id', sa.String(length=64), nullable=True),
    sa.Column('platform', sa.String(length=10), nullable=True),
    sa.Column('app_version', sa.String(length=20), nullable=True),
    sa.Column('event_id', sa.String(length=36), nullable=True),
    sa.Column('surface', sa.String(length=30), nullable=True),
    sa.Column('position', sa.Integer(), nullable=True),
    sa.Column('rec_request_id', sa.String(length=36), nullable=True),
    sa.Column('is_promoted', sa.Boolean(), nullable=False),
    sa.Column('geo_city', sa.String(length=100), nullable=True),
    sa.Column('geo_lat', sa.Float(), nullable=True),
    sa.Column('geo_lon', sa.Float(), nullable=True),
    sa.Column('referrer', sa.String(length=300), nullable=True),
    sa.Column('utm_campaign', sa.String(length=100), nullable=True),
    sa.Column('props', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('client_id')
    )
    with op.batch_alter_table('activity_log', schema=None) as batch_op:
        batch_op.create_index('ix_activity_anon_time', ['anonymous_id', 'occurred_at'], unique=False)
        batch_op.create_index('ix_activity_event_name_time', ['event_id', 'name', 'occurred_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_activity_log_rec_request_id'), ['rec_request_id'], unique=False)
        batch_op.create_index('ix_activity_name_time', ['name', 'occurred_at'], unique=False)
        batch_op.create_index('ix_activity_user_time', ['user_id', 'occurred_at'], unique=False)

    op.create_table('event_features',
    sa.Column('event_id', sa.String(length=36), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('impressions_7d', sa.Integer(), nullable=False),
    sa.Column('clicks_7d', sa.Integer(), nullable=False),
    sa.Column('views_7d', sa.Integer(), nullable=False),
    sa.Column('saves_7d', sa.Integer(), nullable=False),
    sa.Column('orders_7d', sa.Integer(), nullable=False),
    sa.Column('ctr_7d', sa.Float(), nullable=False),
    sa.Column('save_rate_7d', sa.Float(), nullable=False),
    sa.Column('view_to_order_rate_7d', sa.Float(), nullable=False),
    sa.Column('velocity_1h', sa.Integer(), nullable=False),
    sa.Column('velocity_24h', sa.Integer(), nullable=False),
    sa.Column('interest_surge', sa.Float(), nullable=False),
    sa.Column('sell_through_pct', sa.Float(), nullable=True),
    sa.Column('remaining_tickets', sa.Integer(), nullable=True),
    sa.Column('organizer_quality', sa.Float(), nullable=False),
    sa.Column('attendance_reliability', sa.Float(), nullable=True),
    sa.Column('demand_score', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('event_id')
    )
    op.create_table('user_features',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('category_affinity', sa.JSON(), nullable=True),
    sa.Column('tag_affinity', sa.JSON(), nullable=True),
    sa.Column('avg_lead_time_hours', sa.Float(), nullable=True),
    sa.Column('spontaneity_ratio', sa.Float(), nullable=True),
    sa.Column('weekend_share', sa.Float(), nullable=True),
    sa.Column('median_ticket_spend', sa.Float(), nullable=True),
    sa.Column('max_ticket_spend', sa.Float(), nullable=True),
    sa.Column('free_event_share', sa.Float(), nullable=True),
    sa.Column('vip_share', sa.Float(), nullable=True),
    sa.Column('checkout_abandon_rate', sa.Float(), nullable=True),
    sa.Column('home_lat', sa.Float(), nullable=True),
    sa.Column('home_lon', sa.Float(), nullable=True),
    sa.Column('preferred_radius_km', sa.Float(), nullable=True),
    sa.Column('social_affinity_ids', sa.JSON(), nullable=True),
    sa.Column('share_rate', sa.Float(), nullable=True),
    sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lifecycle', sa.String(length=20), nullable=True),
    sa.Column('conversion_propensity', sa.Float(), nullable=True),
    sa.Column('views_30d', sa.Integer(), nullable=False),
    sa.Column('saves_30d', sa.Integer(), nullable=False),
    sa.Column('orders_total', sa.Integer(), nullable=False),
    sa.Column('peak_hours', sa.JSON(), nullable=True),
    sa.Column('co_attendee_ids', sa.JSON(), nullable=True),
    sa.Column('tastemaker_score', sa.Float(), nullable=True),
    sa.Column('segments', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('user_id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('birth_year', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('gender', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('personalized_recs', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('profiling_consent', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('profiling_consent_at', sa.DateTime(timezone=True), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('profiling_consent_at')
        batch_op.drop_column('profiling_consent')
        batch_op.drop_column('personalized_recs')
        batch_op.drop_column('gender')
        batch_op.drop_column('birth_year')

    op.drop_table('user_features')
    op.drop_table('event_features')
    with op.batch_alter_table('activity_log', schema=None) as batch_op:
        batch_op.drop_index('ix_activity_user_time')
        batch_op.drop_index('ix_activity_name_time')
        batch_op.drop_index(batch_op.f('ix_activity_log_rec_request_id'))
        batch_op.drop_index('ix_activity_event_name_time')
        batch_op.drop_index('ix_activity_anon_time')

    op.drop_table('activity_log')
