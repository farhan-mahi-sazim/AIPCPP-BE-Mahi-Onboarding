"""fix enum values to caps

Revision ID: 7ad480d0977d
Revises: d4049905e648
Create Date: 2026-05-10 14:27:52.710186

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7ad480d0977d"
down_revision: str | Sequence[str] | None = "d4049905e648"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'human'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            )
            AND NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'HUMAN'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'human' TO 'HUMAN';
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
            )
            AND NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'AI'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'ai' TO 'AI';
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'HUMAN'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            )
            AND NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'human'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'HUMAN' TO 'human';
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
            )
            AND NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'ai'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'eversionsource')
            ) THEN
                ALTER TYPE eversionsource RENAME VALUE 'AI' TO 'ai';
            END IF;
        END $$;
    """)
