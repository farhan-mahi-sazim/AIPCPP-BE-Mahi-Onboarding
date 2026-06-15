"""add_unique_constraint_file_hash_owner

Revision ID: d4e5f6a7b8c9
Revises: merge_heads_001
Create Date: 2026-06-15 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "merge_heads_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_documents_file_hash_owner'
                AND conrelid = 'documents'::regclass
            ) THEN
                ALTER TABLE documents
                ADD CONSTRAINT uq_documents_file_hash_owner
                UNIQUE (file_hash, owner_id);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_documents_file_hash_owner'
                AND conrelid = 'documents'::regclass
            ) THEN
                ALTER TABLE documents
                DROP CONSTRAINT uq_documents_file_hash_owner;
            END IF;
        END $$;
    """)
