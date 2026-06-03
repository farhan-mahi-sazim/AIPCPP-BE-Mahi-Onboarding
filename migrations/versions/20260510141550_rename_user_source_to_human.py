"""rename user source to human

Revision ID: d4049905e648
Revises: e36f2540d5c1
Create Date: 2026-05-10 14:15:50.821591

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4049905e648"
down_revision: str | Sequence[str] | None = "e36f2540d5c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - idempotent rename."""
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'USER'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'USER' TO 'human';
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'AI'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'AI' TO 'ai';
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'human'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) AND NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'USER'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource ADD VALUE 'human';
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'ai'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) AND NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'AI'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource ADD VALUE 'ai';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade schema - idempotent revert."""
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'human'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'human' TO 'USER';
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'ai'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'ai' TO 'AI';
            END IF;
        END $$;
    """)
