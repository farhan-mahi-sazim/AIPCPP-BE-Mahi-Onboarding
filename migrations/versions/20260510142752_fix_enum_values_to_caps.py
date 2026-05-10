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
    """Upgrade schema."""
    # Custom: Rename enum values back to CAPS
    op.execute("ALTER TYPE eversionsource RENAME VALUE 'human' TO 'HUMAN'")
    op.execute("ALTER TYPE eversionsource RENAME VALUE 'ai' TO 'AI'")


def downgrade() -> None:
    """Downgrade schema."""
    # Custom: Revert to lowercase if needed
    op.execute("ALTER TYPE eversionsource RENAME VALUE 'HUMAN' TO 'human'")
    op.execute("ALTER TYPE eversionsource RENAME VALUE 'AI' TO 'ai'")
