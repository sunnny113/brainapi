"""Add html_body and retry_count columns to email_events table

Revision ID: 001_add_email_columns
Revises: 
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_email_columns'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add html_body column (nullable, up to 8000 characters)
    op.add_column('email_events', sa.Column('html_body', sa.String(8000), nullable=True))
    
    # Add retry_count column (default 0)
    op.add_column('email_events', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    # Remove columns in reverse order
    op.drop_column('email_events', 'retry_count')
    op.drop_column('email_events', 'html_body')
