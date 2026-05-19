"""add_docx_doc_to_file_type

Revision ID: 896e9f6c5f6a
Revises: e36f2540d5c1
Create Date: 2026-05-12 11:58:30.572839

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "896e9f6c5f6a"
down_revision: str | Sequence[str] | None = "e36f2540d5c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE efiletype ADD VALUE 'DOCX'")
    op.execute("ALTER TYPE efiletype ADD VALUE 'DOC'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
