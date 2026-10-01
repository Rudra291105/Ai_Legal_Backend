import os
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User, Workspace, Document, DocumentChunk, DocumentStatus
from app.schemas.document import DocumentResponse
from app.schemas.workspace import (
    WorkspaceCreate, WorkspaceResponse, WorkspaceUploadResponse, UploadFailure,
    WorkspaceChatRequest, WorkspaceChatResponse, WorkspaceSource,
)
from app.services.storage_service import unique_pdf_path
from app.services.pdf_service import save_and_extract_pdf
from app.services.chunking_service import chunk_pages
from app.services.retrieval_service import retrieve_workspace_chunks
from app.services.ai_service import AIService, AIConfigurationError

router = APIRouter(prefix="/api/workspaces", tags=["Legal Study Workspaces"])

MAX_FILES_PER_UPLOAD = 10
NOT_FOUND_ANSWER = "The documents in this workspace do not contain enough information to answer this question."


def owned_workspace(db: Session, user: User, workspace_id: int) -> Workspace:
    ws = db.scalar(select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id))
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


def workspace_dict(ws: Workspace, document_count: int) -> dict:
    return {"id": ws.id, "name": ws.name, "description": ws.description, "document_count": document_count,
            "created_at": ws.created_at, "updated_at": ws.updated_at}


def document_count(db: Session, workspace_id: int) -> int:
    return db.scalar(select(func.count(Document.id)).where(Document.workspace_id == workspace_id)) or 0


@router.post("", response_model=WorkspaceResponse, status_code=201, summary="Create a workspace")
def create_workspace(payload: WorkspaceCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Workspace name is required")
    ws = Workspace(owner_id=user.id, name=name, description=(payload.description or "").strip() or None)
    db.add(ws); db.commit(); db.refresh(ws)
    return workspace_dict(ws, 0)


@router.get("", response_model=list[WorkspaceResponse], summary="List my workspaces")
def list_workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Workspace, func.count(Document.id))
        .outerjoin(Document, Document.workspace_id == Workspace.id)
        .where(Workspace.owner_id == user.id)
        .group_by(Workspace.id)
        .order_by(Workspace.updated_at.desc())
    ).all()
    return [workspace_dict(ws, count) for ws, count in rows]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = owned_workspace(db, user, workspace_id)
    return workspace_dict(ws, document_count(db, ws.id))


@router.delete("/{workspace_id}", status_code=204, summary="Delete a workspace and all its documents")
def delete_workspace(workspace_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = owned_workspace(db, user, workspace_id)
    paths = [d.file_path for d in ws.documents]
    db.delete(ws); db.commit()
    for p in paths:
        try: os.remove(p)
        except OSError: pass


@router.post("/{workspace_id}/documents", response_model=WorkspaceUploadResponse, status_code=201,
             summary="Upload one or more PDFs into a workspace")
async def upload_documents(workspace_id: int, response: Response, files: list[UploadFile] = File(...),
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = owned_workspace(db, user, workspace_id)
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(status_code=400, detail=f"You can upload at most {MAX_FILES_PER_UPLOAD} PDFs at a time")
    existing = {n.lower() for n in db.scalars(select(Document.original_filename).where(Document.workspace_id == ws.id)).all()}
    uploaded: list[Document] = []
    failed: list[UploadFailure] = []
    for f in files:
        name = f.filename or "document.pdf"
        if name.lower() in existing:
            failed.append(UploadFailure(filename=name, detail="A document with this name is already in the workspace"))
            continue
        stored, path = unique_pdf_path()
        try:
            # Reuses the existing PDF pipeline: PyMuPDF page-wise text -> chunks (each keeps page_number).
            size, text, pages = await save_and_extract_pdf(f, path)
            doc = Document(owner_id=user.id, workspace_id=ws.id, title=os.path.splitext(name)[0][:255],
                           original_filename=name[:255], stored_filename=stored, file_path=str(path), file_size=size,
                           page_count=len(pages), status=DocumentStatus.READY, extracted_text=text)
            db.add(doc); db.flush()
            for c in chunk_pages(pages):
                db.add(DocumentChunk(document_id=doc.id, **c))
            db.commit(); db.refresh(doc)
            uploaded.append(doc); existing.add(name.lower())
        except HTTPException as e:
            db.rollback(); path.unlink(missing_ok=True)
            failed.append(UploadFailure(filename=name, detail=str(e.detail)))
        except Exception:
            db.rollback(); path.unlink(missing_ok=True)
            failed.append(UploadFailure(filename=name, detail="Document processing failed"))
    if uploaded:
        ws.updated_at = func.now()
        db.commit()
    else:
        response.status_code = 422
    return WorkspaceUploadResponse(uploaded=[DocumentResponse.model_validate(d, from_attributes=True) for d in uploaded], failed=failed)


@router.get("/{workspace_id}/documents", response_model=list[DocumentResponse])
def list_workspace_documents(workspace_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = owned_workspace(db, user, workspace_id)
    return list(db.scalars(select(Document).where(Document.workspace_id == ws.id).order_by(Document.created_at.desc())).all())


@router.delete("/{workspace_id}/documents/{document_id}", status_code=204)
def delete_workspace_document(workspace_id: int, document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = owned_workspace(db, user, workspace_id)
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.workspace_id == ws.id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found in this workspace")
    path = doc.file_path
    db.delete(doc); db.commit()
    try: os.remove(path)
    except OSError: pass


@router.post("/{workspace_id}/chat", response_model=WorkspaceChatResponse, summary="Ask a question across a workspace's documents")
def workspace_chat(workspace_id: int, payload: WorkspaceChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ws = owned_workspace(db, user, workspace_id)
    if document_count(db, ws.id) == 0:
        raise HTTPException(status_code=409, detail="Upload at least one PDF to this workspace before asking questions")
    question = payload.question.strip()
    chunks = retrieve_workspace_chunks(db, ws.id, question)
    if not chunks:  # nothing relevant: do not call Gemini, do not send unrelated text
        return WorkspaceChatResponse(answer=NOT_FOUND_ANSWER, sources=[])
    try:
        ai = AIService()
    except AIConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e))
    excerpts = [(i, c.document_name, c.page_number, c.content) for i, c in enumerate(chunks, start=1)]
    try:
        result = ai.ask_workspace(excerpts, question)
    except Exception as e:
        raise HTTPException(status_code=502, detail="The AI service could not answer right now. Please try again.") from e
    answer = result["answer"] or NOT_FOUND_ANSWER
    if not result["found"]:
        return WorkspaceChatResponse(answer=answer, sources=[])
    cited = {n for n in result["cited"] if 1 <= n <= len(chunks)} or set(range(1, len(chunks) + 1))
    sources, seen = [], set()
    for i, c in enumerate(chunks, start=1):
        key = (c.document_id, c.page_number)
        if i in cited and key not in seen:
            seen.add(key)
            sources.append(WorkspaceSource(document_id=c.document_id, document_name=c.document_name, page=c.page_number, snippet=c.content[:500]))
    return WorkspaceChatResponse(answer=answer, sources=sources)
