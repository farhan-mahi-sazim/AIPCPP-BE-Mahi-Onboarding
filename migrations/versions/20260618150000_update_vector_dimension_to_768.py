"""update_vector_dimension_to_768

Revision ID: f1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-06-18 15:00:00.000000

"""

from collections.abc import Sequence

import pgvector
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Truncate table to prevent casting errors between different dimensions
    op.execute("TRUNCATE TABLE document_chunks;")

    # 2. Alter column type
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=3072),
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=768),
        existing_nullable=True,
    )


def downgrade() -> None:
    # 1. Truncate table
    op.execute("TRUNCATE TABLE document_chunks;")

    # 2. Revert column type
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=768),
        type_=pgvector.sqlalchemy.vector.VECTOR(dim=3072),
        existing_nullable=True,
    )
