"""Add owner_promotion_requests table.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "owner_promotion_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_owner_promotion_requests_status",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_owner_promotion_requests_requester_id",
        "owner_promotion_requests",
        ["requester_id"],
    )
    op.create_index(
        "ix_owner_promotion_requests_status",
        "owner_promotion_requests",
        ["status"],
    )
    op.create_index(
        "ix_owner_promotion_requests_created_at",
        "owner_promotion_requests",
        ["created_at"],
    )
    op.create_index(
        "uq_owner_promotion_requests_pending_requester",
        "owner_promotion_requests",
        ["requester_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_owner_promotion_requests_pending_requester",
        table_name="owner_promotion_requests",
    )
    op.drop_index(
        "ix_owner_promotion_requests_created_at",
        table_name="owner_promotion_requests",
    )
    op.drop_index(
        "ix_owner_promotion_requests_status",
        table_name="owner_promotion_requests",
    )
    op.drop_index(
        "ix_owner_promotion_requests_requester_id",
        table_name="owner_promotion_requests",
    )
    op.drop_table("owner_promotion_requests")
