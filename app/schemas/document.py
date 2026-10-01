from datetime import datetime
from pydantic import BaseModel, Field

class DocumentResponse(BaseModel):
    id: int; title: str; original_filename: str; file_size: int; page_count: int; document_type: str | None; status: str; created_at: datetime

class DocumentDetail(DocumentResponse):
    updated_at: datetime

class Source(BaseModel):
    page: int
    snippet: str

class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)

class AskResponse(BaseModel):
    answer: str
    sources: list[Source]

class SummaryResponse(BaseModel):
    overview: str
    important_clauses: list[str]
    parties: list[str]
    obligations: list[str]
    payments: list[str]
    dates: list[str]
    termination: list[str]
    confidentiality: list[str]
    potentially_important_clauses: list[str]

class SimplifyResponse(BaseModel):
    explanation: str
