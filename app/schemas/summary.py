from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.schemas.transaction import TransactionResponse

class JobSummaryResponse(BaseModel):
    id: int
    job_id: str
    total_spend_inr: float
    total_spend_usd: float
    top_merchants: Optional[List[Dict[str, Any]]] = None
    category_breakdown: Optional[Dict[str, float]] = None
    anomaly_count: int
    narrative: Optional[str] = None
    risk_level: Optional[str] = None

    class Config:
        from_attributes = True

# Response for results endpoint /jobs/{job_id}/results
class JobResultsResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    summary: Optional[JobSummaryResponse] = None
    transactions: List[TransactionResponse]
    anomalies: List[TransactionResponse]
    category_breakdown: Dict[str, float]

    class Config:
        from_attributes = True
