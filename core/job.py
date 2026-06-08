from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any

class Job(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str
    title: str
    company: str
    location: Optional[str] = None
    url: str
    apply_url: Optional[str] = None
    salary: Optional[str] = None
    applied: bool = False
    status: str = "PENDING"
    description: Optional[str] = None
    is_external: bool = False
    skipped: bool = False
    skipped_reason: Optional[str] = None

class Question(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str
    text: str
    type: str # 'text', 'select', 'checkbox', 'radio'
    options: Optional[List[str]] = None
    required: bool = True
    answered: bool = False

class ApplicationResult(BaseModel):
    job_id: str
    success: bool
    reason: Optional[str] = None
    unanswered_questions: List[Any] = Field(default_factory=list)
