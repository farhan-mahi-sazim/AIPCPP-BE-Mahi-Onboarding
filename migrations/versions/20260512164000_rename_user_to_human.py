"""rename user source to human

Revision ID: a1b2c3d4e5f6
Revises: 896e9f6c5f6a
Create Date: 2026-05-12 16:40:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "896e9f6c5f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename USER to HUMAN in eversionsource enum (idempotent)."""
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'USER'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'USER' TO 'HUMAN';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert HUMAN back to USER (idempotent)."""
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'HUMAN'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'HUMAN' TO 'USER';
            END IF;
        END $$;
    """)
