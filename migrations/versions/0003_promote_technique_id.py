"""Promote technique_id to a typed indexed document column.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("technique_id", sa.String(length=32), nullable=True))
    op.execute(
        sa.text(
            "UPDATE documents "
            "SET technique_id = metadata->>'technique_id' "
            "WHERE metadata ? 'technique_id'"
        )
    )
    op.create_index(
        "ix_documents_technique_id",
        "documents",
        ["technique_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_technique_id", table_name="documents")
    op.drop_column("documents", "technique_id")
