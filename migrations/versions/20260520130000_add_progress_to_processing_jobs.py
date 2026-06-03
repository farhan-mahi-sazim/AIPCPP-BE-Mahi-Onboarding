"""add_progress_to_processing_jobs

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-20 13:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'processing_jobs'
                AND column_name = 'progress'
            ) THEN
                ALTER TABLE processing_jobs ADD COLUMN progress INTEGER;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'processing_jobs'
                AND column_name = 'progress'
            ) THEN
                ALTER TABLE processing_jobs DROP COLUMN progress;
            END IF;
        END $$;
    """)
