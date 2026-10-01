from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.document import DocumentResponse


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime


class UploadFailure(BaseModel):
    filename: str
    detail: str


class WorkspaceUploadResponse(BaseModel):
    uploaded: list[DocumentResponse]
    failed: list[UploadFailure]


class WorkspaceChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)


class WorkspaceSource(BaseModel):
    document_id: int
    document_name: str
    page: int
    snippet: str


class WorkspaceChatResponse(BaseModel):
    answer: str
    sources: list[WorkspaceSource]
