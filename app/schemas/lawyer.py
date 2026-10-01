from datetime import datetime
from pydantic import BaseModel, Field

DOCUMENT_TYPES = ["Rental Agreement", "Employment Agreement", "Non-Disclosure Agreement", "Service Agreement", "Freelance Agreement", "Legal Notice"]

class LawyerDocumentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    document_type: str
    input_data: dict

class LawyerDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    document_type: str | None = None
    input_data: dict | None = None
    generated_content: str | None = None

class LawyerDocumentResponse(BaseModel):
    id: int; title: str; document_type: str; input_data: dict; generated_content: str; status: str; created_at: datetime; updated_at: datetime

class FinalizeResponse(BaseModel):
    id: int
    status: str
    content: str
