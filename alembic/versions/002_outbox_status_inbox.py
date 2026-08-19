from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_outbox_status_inbox"
down_revision: Union[str, None] = "001_payments_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outbox",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="NEW",
        ),
    )
    op.add_column(
        "outbox",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "outbox",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text("UPDATE outbox SET status = 'PROCESSED' WHERE published_at IS NOT NULL")
    )
    op.drop_index("ix_outbox_unpublished", table_name="outbox")
    op.create_index(
        "ix_outbox_pending",
        "outbox",
        ["created_at"],
        postgresql_where=sa.text("status IN ('NEW', 'PROCESSING')"),
    )
    op.create_table(
        "inbox",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("message_id"),
    )


def downgrade() -> None:
    op.drop_table("inbox")
    op.drop_index("ix_outbox_pending", table_name="outbox")
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.drop_column("outbox", "claimed_at")
    op.drop_column("outbox", "retry_count")
    op.drop_column("outbox", "status")
