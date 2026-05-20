"""merge_heads

Revision ID: merge_heads_001
Revises: 7ad480d0977d, c3d4e5f6a7b8
Create Date: 2026-05-20 15:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "merge_heads_001"
down_revision: str | Sequence[str] | None = ("7ad480d0977d", "c3d4e5f6a7b8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'documents'
                AND column_name = 'file_hash'
            ) THEN
                ALTER TABLE documents ADD COLUMN file_hash VARCHAR(64);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'documents'
                AND indexname = 'ix_documents_file_hash'
            ) THEN
                CREATE INDEX ix_documents_file_hash ON documents (file_hash);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'documents'
                AND indexname = 'ix_documents_file_hash'
            ) THEN
                DROP INDEX ix_documents_file_hash;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'documents'
                AND column_name = 'file_hash'
            ) THEN
                ALTER TABLE documents DROP COLUMN file_hash;
            END IF;
        END $$;
    """)
