import os
import time
import logging
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.workers.celery_app import celery_app
from app.db import SessionLocal
from app.models.job import Job, JobStatus
from app.models.transaction import Transaction
from app.models.summary import JobSummary
from app.services.cleaning import clean_transactions_dataframe
from app.services.anomaly import detect_anomalies_dataframe
from app.services.report import (
    generate_spend_totals,
    generate_category_breakdown,
    generate_top_merchants
)
from app.services.llm import batch_classify_merchants, generate_spending_narrative

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_job_progress(db: Session, job: Job, progress: int, status: JobStatus = None):
    """
    Helper to update and commit job progress details.
    """
    job.progress = progress
    if status:
        job.status = status
    db.add(job)
    db.commit()
    logger.info(f"Job {job.id} progress updated to {progress}% ({job.status.value})")

@celery_app.task(bind=True, max_retries=3)
def process_csv_task(self, job_id: str):
    """
    Asynchronous task that cleans, detects anomalies, classifies using LLM,
    summarizes, and saves the financial transaction CSV.
    """
    start_time = time.time()
    db: Session = SessionLocal()
    
    # 1. Fetch the Job
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        logger.error(f"Job {job_id} not found in database.")
        db.close()
        return f"Job {job_id} not found"
        
    logger.info(f"Starting async processing for Job: {job.id}")
    
    try:
        # Update status to processing
        update_job_progress(db, job, 10, JobStatus.PROCESSING)
        
        # 2. Read file from disk
        if not os.path.exists(job.file_path):
            raise FileNotFoundError(f"Uploaded CSV not found at: {job.file_path}")
            
        df = pd.read_csv(job.file_path)
        job.row_count_raw = len(df)
        db.add(job)
        db.commit()
        
        # 3. Clean Data (25% progress)
        df, raw_count, clean_count = clean_transactions_dataframe(df)
        update_job_progress(db, job, 25)
        
        # 4. Detect Anomalies (50% progress)
        df = detect_anomalies_dataframe(df)
        update_job_progress(db, job, 50)
        
        # 5. Classify missing categories using LLM (75% progress)
        df = classify_transactions_step(df)
        update_job_progress(db, job, 75)
        
        # 6. Generate Summary (90% progress)
        summary_data = generate_summary_step(df)
        update_job_progress(db, job, 90)
        
        # 7. Save Results (100% progress)
        save_results_step(db, job, df, summary_data, clean_count, start_time)
        
        logger.info(f"Job {job.id} completed successfully in {time.time() - start_time:.2f} seconds")
        return f"Job {job_id} processed successfully"
        
    except Exception as e:
        logger.exception(f"Error executing pipeline for Job {job_id}: {str(e)}")
        db.rollback()
        # Mark job as failed
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        job.processing_time_seconds = time.time() - start_time
        db.add(job)
        db.commit()
        return f"Job {job_id} failed: {str(e)}"
    finally:
        db.close()

# Modular Steps:
def classify_transactions_step(df: pd.DataFrame) -> pd.DataFrame:
    """
    Finds unique merchants for transactions that do not have a category,
    classifies them using the Gemini LLM service, and updates the DataFrame.
    """
    # Find rows with missing categories
    missing_mask = df['category'].isna()
    
    # Add metadata columns if they don't exist
    df['llm_category'] = None
    df['llm_failed'] = False
    
    if not missing_mask.any():
        logger.info("No missing categories found. Skipping LLM classification.")
        return df
        
    # Get unique merchants for missing category rows
    missing_merchants = df.loc[missing_mask, 'merchant'].dropna().unique().tolist()
    
    if not missing_merchants:
        # If there are missing categories but no merchants, just default them
        df.loc[missing_mask, 'category'] = "Uncategorised"
        return df
        
    logger.info(f"Found {len(missing_merchants)} unique merchants needing classification.")
    
    try:
        # Call batch LLM classification service
        classifications = batch_classify_merchants(missing_merchants)
        
        # Map categories back to DataFrame
        for idx, row in df[missing_mask].iterrows():
            merchant = row['merchant']
            assigned_cat = classifications.get(merchant)
            if assigned_cat:
                df.at[idx, 'category'] = assigned_cat
                df.at[idx, 'llm_category'] = assigned_cat
            else:
                df.at[idx, 'category'] = "Uncategorised"
                df.at[idx, 'llm_failed'] = True
                
    except Exception as e:
        logger.error(f"LLM Classification failed, falling back to 'Uncategorised'. Details: {str(e)}")
        # If all retries failed inside services/llm.py, default missing rows to "Uncategorised"
        df.loc[missing_mask, 'category'] = "Uncategorised"
        df.loc[missing_mask, 'llm_failed'] = True
        
    return df

def generate_summary_step(df: pd.DataFrame) -> dict:
    """
    Computes mathematical report metrics, calls the LLM to generate narrative summary
    and risk level, and returns the combined data dictionary.
    """
    # 1. Math totals
    totals = generate_spend_totals(df)
    total_spend_inr = totals.get("INR", 0.0)
    total_spend_usd = totals.get("USD", 0.0)
    
    # 2. Top Merchants
    top_merchants = generate_top_merchants(df, limit=3)
    
    # 3. Category Breakdown
    category_breakdown = generate_category_breakdown(df)
    
    # 4. Anomaly Count
    anomaly_count = int(df['is_anomaly'].sum())
    
    # 5. Narrative & Risk Level from LLM
    try:
        llm_response = generate_spending_narrative(
            total_spend_inr=total_spend_inr,
            total_spend_usd=total_spend_usd,
            top_merchants=top_merchants,
            anomaly_count=anomaly_count
        )
        
        narrative = llm_response.narrative
        risk_level = llm_response.risk_level
        raw_llm = llm_response.model_dump()
        
    except Exception as e:
        logger.error(f"Failed to generate LLM summary narrative, utilizing fallback. Details: {str(e)}")
        # Fallback narrative
        narrative = (
            f"Automated fallback report. Processed {len(df)} financial transactions. "
            f"Calculated spend includes INR {total_spend_inr} and USD {total_spend_usd}. "
            f"Identified {anomaly_count} potential anomalies."
        )
        # Default risk evaluation
        risk_level = "high" if anomaly_count > 5 else ("medium" if anomaly_count > 0 else "low")
        raw_llm = {"error": str(e), "fallback_used": True}
        
    return {
        "total_spend_inr": total_spend_inr,
        "total_spend_usd": total_spend_usd,
        "top_merchants": top_merchants,
        "category_breakdown": category_breakdown,
        "anomaly_count": anomaly_count,
        "narrative": narrative,
        "risk_level": risk_level,
        "raw_llm_response": raw_llm
    }

def save_results_step(db: Session, job: Job, df: pd.DataFrame, summary_data: dict, clean_count: int, start_time: float):
    """
    Saves cleaned transactions using SQLAlchemy bulk inserts and persists the job summary.
    Marks job completed.
    """
    # 1. Bulk insert transactions
    transaction_records = []
    for _, row in df.iterrows():
        txn = Transaction(
            job_id=job.id,
            txn_id=row.get('txn_id') if pd.notna(row.get('txn_id')) else None,
            date=row['date'],
            merchant=row['merchant'],
            amount=float(row['amount']),
            currency=row['currency'],
            status=row['status'],
            category=row['category'],
            account_id=row['account_id'],
            notes=row.get('notes') if pd.notna(row.get('notes')) else None,
            is_anomaly=bool(row['is_anomaly']),
            anomaly_reason=row['anomaly_reason'],
            llm_category=row['llm_category'],
            llm_failed=bool(row['llm_failed'])
        )
        transaction_records.append(txn)
        
    # Bulk save to DB
    db.bulk_save_objects(transaction_records)
    
    # 2. Save summary
    summary = JobSummary(
        job_id=job.id,
        total_spend_inr=summary_data["total_spend_inr"],
        total_spend_usd=summary_data["total_spend_usd"],
        top_merchants=summary_data["top_merchants"],
        category_breakdown=summary_data["category_breakdown"],
        anomaly_count=summary_data["anomaly_count"],
        narrative=summary_data["narrative"],
        risk_level=summary_data["risk_level"],
        raw_llm_response=summary_data["raw_llm_response"]
    )
    db.add(summary)
    
    # 3. Update Job model metadata
    job.row_count_clean = clean_count
    job.processing_time_seconds = time.time() - start_time
    job.completed_at = datetime.now(timezone.utc)
    job.status = JobStatus.COMPLETED
    job.progress = 100
    
    db.add(job)
    db.commit()
