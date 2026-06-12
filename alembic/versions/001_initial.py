"""initial migration

Revision ID: 001_initial
Revises: 
Create Date: 2026-06-12 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ENUM

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create JobStatus PostgreSQL Enum type if it doesn't exist
    conn = op.get_bind()
    type_exists = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'jobstatus')")).scalar()
    if not type_exists:
        op.execute("CREATE TYPE jobstatus AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')")

    # 2. Create 'jobs' table
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('status', ENUM('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', name='jobstatus', create_type=False), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('row_count_raw', sa.Integer(), nullable=True),
        sa.Column('row_count_clean', sa.Integer(), nullable=True),
        sa.Column('processing_time_seconds', sa.Float(), nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for 'jobs' table
    op.create_index('idx_job_status', 'jobs', ['status'], unique=False)
    op.create_index('idx_job_created', 'jobs', ['created_at'], unique=False)

    # 3. Create 'transactions' table
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('txn_id', sa.String(length=50), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('merchant', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('account_id', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.String(length=512), nullable=True),
        sa.Column('is_anomaly', sa.Boolean(), nullable=False),
        sa.Column('anomaly_reason', sa.String(length=255), nullable=True),
        sa.Column('llm_category', sa.String(length=100), nullable=True),
        sa.Column('llm_failed', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for 'transactions' table
    op.create_index('idx_transaction_job', 'transactions', ['job_id'], unique=False)
    op.create_index('idx_transaction_txn_id', 'transactions', ['txn_id'], unique=False)
    op.create_index('idx_transaction_account_id', 'transactions', ['account_id'], unique=False)

    # 4. Create 'job_summaries' table
    op.create_table(
        'job_summaries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('total_spend_inr', sa.Float(), nullable=False),
        sa.Column('total_spend_usd', sa.Float(), nullable=False),
        sa.Column('top_merchants', JSONB(), nullable=True),
        sa.Column('category_breakdown', JSONB(), nullable=True),
        sa.Column('raw_llm_response', JSONB(), nullable=True),
        sa.Column('anomaly_count', sa.Integer(), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=True),
        sa.Column('risk_level', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    
    # Create index for 'job_summaries' table
    op.create_index('idx_summary_job', 'job_summaries', ['job_id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index('idx_summary_job', table_name='job_summaries')
    op.drop_table('job_summaries')
    
    op.drop_index('idx_transaction_account_id', table_name='transactions')
    op.drop_index('idx_transaction_txn_id', table_name='transactions')
    op.drop_index('idx_transaction_job', table_name='transactions')
    op.drop_table('transactions')
    
    op.drop_index('idx_job_created', table_name='jobs')
    op.drop_index('idx_job_status', table_name='jobs')
    op.drop_table('jobs')
    
    # Drop JobStatus PostgreSQL Enum
    op.execute("DROP TYPE jobstatus")
