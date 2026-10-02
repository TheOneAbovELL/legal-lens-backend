"""conversations, messages and message evidence

Revision ID: 0002_conversations
Revises: 0001_create_users
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_conversations"
down_revision = "0001_create_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conversations_user_updated", "conversations", ["user_id", "updated_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="complete"),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("complexity", sa.String(16), nullable=True),
        sa.Column("intent", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
    )
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])

    op.create_table(
        "message_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("citation_id", sa.String(16), nullable=False),
        sa.Column("document_id", sa.String(128), nullable=False),
        sa.Column("chunk_id", sa.String(64), nullable=True),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("act", sa.String(64), nullable=True),
        sa.Column("section", sa.String(32), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("score", sa.Float(), nullable=True),
    )
    op.create_index("ix_message_evidence_message", "message_evidence", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_message_evidence_message", table_name="message_evidence")
    op.drop_table("message_evidence")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_table("conversations")
