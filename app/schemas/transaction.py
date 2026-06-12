from pydantic import BaseModel
from datetime import date
from typing import Optional

class TransactionResponse(BaseModel):
    id: int
    job_id: str
    txn_id: Optional[str] = None
    date: date
    merchant: str
    amount: float
    currency: str
    status: str
    category: Optional[str] = None
    account_id: str
    notes: Optional[str] = None
    is_anomaly: bool
    anomaly_reason: Optional[str] = None
    llm_category: Optional[str] = None
    llm_failed: bool

    class Config:
        from_attributes = True
