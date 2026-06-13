"""Add processed_events table for durable idempotency.

Revision ID: 002
Revises: 001
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the processed_events table."""
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Drop the processed_events table."""
    op.drop_table("processed_events")
