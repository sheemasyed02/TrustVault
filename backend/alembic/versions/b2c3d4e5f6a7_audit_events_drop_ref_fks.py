"""Drop audit_events FKs so denial events can record unknown IDs.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-21 19:30:00.000000

Audit rows must be able to record IDOR / guessed document IDs and login
failures for emails that do not map to a committed user row visible to an
independent denial transaction. Referential indexes are retained.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "audit_events_actor_id_fkey",
        "audit_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "audit_events_document_id_fkey",
        "audit_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "audit_events_target_user_id_fkey",
        "audit_events",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "audit_events_actor_id_fkey",
        "audit_events",
        "users",
        ["actor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "audit_events_document_id_fkey",
        "audit_events",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "audit_events_target_user_id_fkey",
        "audit_events",
        "users",
        ["target_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
