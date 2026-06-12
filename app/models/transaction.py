from sqlalchemy import Column, Integer, Float, String, Date, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.db import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    txn_id = Column(String(50), nullable=True)
    date = Column(Date, nullable=False)
    merchant = Column(String(255), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False)
    category = Column(String(100), nullable=True)  # Nullable initially for LLM categorization
    account_id = Column(String(50), nullable=False)
    notes = Column(String(512), nullable=True)

    # Anomaly Detection Fields
    is_anomaly = Column(Boolean, default=False, nullable=False)
    anomaly_reason = Column(String(255), nullable=True)

    # LLM Categorization Metadata
    llm_category = Column(String(100), nullable=True)
    llm_failed = Column(Boolean, default=False, nullable=False)

    # Relationship back to Job
    job = relationship("Job", back_populates="transactions")

# Establish models relationships
from app.models.job import Job
Job.transactions = relationship("Transaction", back_populates="job", cascade="all, delete-orphan")

# Database Indexes
Index("idx_transaction_job", Transaction.job_id)
Index("idx_transaction_txn_id", Transaction.txn_id)
Index("idx_transaction_account_id", Transaction.account_id)
