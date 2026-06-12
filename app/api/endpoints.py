import io
import os
import csv
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.db import get_db
from app.models.job import Job, JobStatus
from app.models.transaction import Transaction
from app.models.summary import JobSummary
from app.schemas.job import JobResponse
from app.schemas.transaction import TransactionResponse
from app.schemas.summary import JobResultsResponse, JobSummaryResponse
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/jobs/upload", status_code=status.HTTP_201_CREATED)
async def upload_transactions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Accepts CSV file upload, registers a pending job, saves file to local directory,
    and enqueues the processing task to Celery.
    """
    # Verify extension
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed."
        )

    # 1. Create a job record to obtain a job ID
    job = Job(
        filename=file.filename,
        file_path="TEMP",  # Updated once saved
        status=JobStatus.PENDING,
        progress=0
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 2. Write file to disk
    job_file_name = f"job_{job.id}.csv"
    destination_path = os.path.join(settings.UPLOAD_DIR, job_file_name)
    
    try:
        with open(destination_path, "wb") as buffer:
            # Read in chunks to prevent memory bloat
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
    except Exception as e:
        logger.error(f"Failed to write uploaded file for job {job.id}: {str(e)}")
        job.status = JobStatus.FAILED
        job.error_message = f"File write error: {str(e)}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file."
        )

    # Update job path
    job.file_path = destination_path
    db.add(job)
    db.commit()
    db.refresh(job)

    # 3. Enqueue celery task
    from app.workers.tasks import process_csv_task
    process_csv_task.delay(job.id)

    return {
        "job_id": job.id,
        "status": job.status.value,
        "progress": job.progress
    }


@router.get("/jobs/{job_id}/status", response_model=JobResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Returns the current status, progress, and metadata of a job.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found."
        )
    return job


@router.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(job_id: str, db: Session = Depends(get_db)):
    """
    Returns the complete analysis results of a job, including raw/cleaned records,
    detected anomalies, spending aggregates, and LLM narrative.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found."
        )

    if job.status != JobStatus.COMPLETED:
        # Return partial status
        return {
            "job_id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "summary": None,
            "transactions": [],
            "anomalies": [],
            "category_breakdown": {}
        }

    # Fetch transactions and summary
    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()
    anomalies = [t for t in transactions if t.is_anomaly]
    summary = db.query(JobSummary).filter(JobSummary.job_id == job_id).first()

    category_breakdown = summary.category_breakdown if (summary and summary.category_breakdown) else {}

    return {
        "job_id": job.id,
        "status": job.status.value,
        "progress": job.progress,
        "summary": summary,
        "transactions": transactions,
        "anomalies": anomalies,
        "category_breakdown": category_breakdown
    }


@router.get("/jobs/{job_id}/download")
def download_cleaned_csv(job_id: str, db: Session = Depends(get_db)):
    """
    Streams the cleaned, normalized database transaction records back as a downloadable CSV.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found."
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot download results. Job status is '{job.status.value}'."
        )

    # Fetch transactions from DB
    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()

    def generate():
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers
        writer.writerow([
            "txn_id", "date", "merchant", "amount", "currency", 
            "status", "category", "account_id", "notes", 
            "is_anomaly", "anomaly_reason", "llm_category", "llm_failed"
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for t in transactions:
            writer.writerow([
                t.txn_id or "",
                t.date.isoformat() if t.date else "",
                t.merchant,
                t.amount,
                t.currency,
                t.status,
                t.category or "Uncategorised",
                t.account_id,
                t.notes or "",
                t.is_anomaly,
                t.anomaly_reason or "",
                t.llm_category or "",
                t.llm_failed
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    filename = f"cleaned_transactions_{job_id}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/jobs", response_model=List[JobResponse])
def list_jobs(
    status: Optional[JobStatus] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Lists historical processing jobs, supporting filters by status.
    """
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
        
    return query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    System diagnostic check for database and api availability.
    """
    try:
        # Execute basic query to check DB
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Healthcheck database connection error: {str(e)}")
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "api": "healthy",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc)
    }


@router.get("/analytics")
def get_dashboard_analytics(db: Session = Depends(get_db)):
    """
    Returns platform-wide aggregate intelligence KPIs (total spends, anomaly rates, risk level summaries).
    """
    # 1. Spends aggregation
    sums = db.query(
        func.sum(JobSummary.total_spend_inr).label("inr_total"),
        func.sum(JobSummary.total_spend_usd).label("usd_total"),
        func.sum(JobSummary.anomaly_count).label("anomaly_total"),
        func.count(JobSummary.id).label("job_count")
    ).first()
    
    # 2. Total clean transaction count
    txn_count = db.query(func.count(Transaction.id)).scalar() or 0
    
    # 3. Categorical counts
    category_counts = db.query(
        Transaction.category,
        func.count(Transaction.id).label("count")
    ).group_by(Transaction.category).all()
    
    category_distribution = {
        cat or "Uncategorised": count for cat, count in category_counts
    }
    
    # 4. Risk distribution
    risk_counts = db.query(
        JobSummary.risk_level,
        func.count(JobSummary.id).label("count")
    ).group_by(JobSummary.risk_level).all()
    
    risk_distribution = {
        risk or "unknown": count for risk, count in risk_counts
    }

    return {
        "overall_spend_inr": round(float(sums.inr_total or 0.0), 2),
        "overall_spend_usd": round(float(sums.usd_total or 0.0), 2),
        "total_anomalies_detected": int(sums.anomaly_total or 0),
        "total_jobs_processed": int(sums.job_count or 0),
        "total_transactions_stored": txn_count,
        "category_distribution": category_distribution,
        "job_risk_distribution": risk_distribution
    }


@router.get("/transactions/search", response_model=List[TransactionResponse])
def search_transactions(
    query: Optional[str] = Query(None, description="Search merchant name"),
    category: Optional[str] = Query(None, description="Filter by category"),
    is_anomaly: Optional[bool] = Query(None, description="Filter by anomaly state"),
    min_amount: Optional[float] = Query(None, description="Minimum amount"),
    max_amount: Optional[float] = Query(None, description="Maximum amount"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Search engine query filter for transaction database.
    """
    q = db.query(Transaction)
    if query:
        q = q.filter(Transaction.merchant.ilike(f"%{query}%"))
    if category:
        q = q.filter(Transaction.category.ilike(category))
    if is_anomaly is not None:
        q = q.filter(Transaction.is_anomaly == is_anomaly)
    if min_amount is not None:
        q = q.filter(Transaction.amount >= min_amount)
    if max_amount is not None:
        q = q.filter(Transaction.amount <= max_amount)

    return q.limit(limit).all()
