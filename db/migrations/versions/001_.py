"""Create tables for manufactors and devices

Revision ID: 001
Revises:
Create Date: 2026-10-19 17:39:47.648628

"""

from alembic import op
import sqlalchemy as sa


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manufactors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column(
            "device_type",
            sa.Enum("TERMINAL", "ROUTER", "BRACKET", name="devicetype"),
            nullable=False,
        ),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("balance_count", sa.Integer(), nullable=False),
        sa.Column("manufactor_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["manufactor_id"],
            ["manufactors.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("devices")
    op.drop_table("manufactors")
