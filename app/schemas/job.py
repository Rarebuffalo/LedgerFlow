from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.job import JobStatus

class JobBase(BaseModel):
    filename: str

class JobCreate(JobBase):
    file_path: str

class JobResponse(JobBase):
    id: str
    status: JobStatus
    progress: int
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    processing_time_seconds: Optional[float] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
