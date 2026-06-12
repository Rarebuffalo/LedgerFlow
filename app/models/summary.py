from sqlalchemy import Column, Integer, Float, String, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from app.db import Base

# Dialect-independent JSONB type
JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

class JobSummary(Base):
    __tablename__ = "job_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    total_spend_inr = Column(Float, default=0.0, nullable=False)
    total_spend_usd = Column(Float, default=0.0, nullable=False)
    
    # Store dynamic structure using JSONB
    top_merchants = Column(JSON_TYPE, nullable=True)         # List of top merchants
    category_breakdown = Column(JSON_TYPE, nullable=True)    # Breakdown of spend by category
    raw_llm_response = Column(JSON_TYPE, nullable=True)      # Raw response from LLM for auditable history
    
    anomaly_count = Column(Integer, default=0, nullable=False)
    narrative = Column(Text, nullable=True)
    risk_level = Column(String(20), nullable=True)  # low, medium, high

    # Relationship back to Job
    job = relationship("Job", back_populates="summary")

# Associate back to Job model
from app.models.job import Job
Job.summary = relationship("JobSummary", back_populates="job", uselist=False, cascade="all, delete-orphan")

# Database Indexes
Index("idx_summary_job", JobSummary.job_id)
