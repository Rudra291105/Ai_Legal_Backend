import json, os
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models import User, Document, DocumentChunk, DocumentStatus, ChatSession, ChatMessage
from app.schemas.document import DocumentResponse, DocumentDetail, AskRequest, AskResponse, Source, SummaryResponse, SimplifyResponse
from app.services.storage_service import unique_pdf_path
from app.services.pdf_service import save_and_extract_pdf
from app.services.chunking_service import chunk_pages
from app.services.retrieval_service import retrieve_chunks
from app.services.ai_service import AIService, AIConfigurationError

router=APIRouter(prefix="/api/documents", tags=["Documents"])

def owned(db,user,doc_id):
    doc=db.scalar(select(Document).where(Document.id==doc_id, Document.owner_id==user.id))
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    return doc

def ai_or_error():
    try: return AIService()
    except AIConfigurationError as e: raise HTTPException(status_code=503, detail=str(e))

@router.post("/upload", response_model=DocumentResponse, status_code=201, summary="Upload and process a PDF")
async def upload(file: UploadFile=File(...), user: User=Depends(get_current_user), db: Session=Depends(get_db)):
    stored,path=unique_pdf_path()
    title=os.path.splitext(file.filename or "Untitled document")[0]
    try:
        size,text,pages=await save_and_extract_pdf(file,path)
        doc=Document(owner_id=user.id,title=title[:255],original_filename=file.filename or "document.pdf",stored_filename=stored,file_path=str(path),file_size=size,page_count=len(pages),status=DocumentStatus.READY,extracted_text=text)
        db.add(doc); db.flush()
        for c in chunk_pages(pages): db.add(DocumentChunk(document_id=doc.id,**c))
        db.commit(); db.refresh(doc); return doc
    except HTTPException: path.unlink(missing_ok=True); raise
    except Exception as e:
        path.unlink(missing_ok=True); db.rollback(); raise HTTPException(status_code=500, detail="Document processing failed") from e

@router.get("", response_model=list[DocumentResponse])
def list_documents(user: User=Depends(get_current_user), db: Session=Depends(get_db)):
    return list(db.scalars(select(Document).where(Document.owner_id==user.id, Document.workspace_id.is_(None)).order_by(Document.created_at.desc())).all())

@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)): return owned(db,user,document_id)

@router.get("/{document_id}/text")
def get_text(document_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    doc=owned(db,user,document_id); return {"id":doc.id,"text":doc.extracted_text}

@router.delete("/{document_id}", status_code=204)
def delete_document(document_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    doc=owned(db,user,document_id); path=doc.file_path; db.delete(doc); db.commit()
    try: os.remove(path)
    except OSError: pass

@router.post("/{document_id}/simplify", response_model=SimplifyResponse)
def simplify(document_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    doc=owned(db,user,document_id)
    if doc.status != DocumentStatus.READY: raise HTTPException(status_code=409, detail="Document is not ready")
    return {"explanation":ai_or_error().simplify(doc.extracted_text)}

@router.post("/{document_id}/summarize", response_model=SummaryResponse)
def summarize(document_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    doc=owned(db,user,document_id)
    if doc.status != DocumentStatus.READY: raise HTTPException(status_code=409, detail="Document is not ready")
    return ai_or_error().summarize(doc.extracted_text)

@router.post("/{document_id}/ask", response_model=AskResponse)
def ask(document_id:int,payload:AskRequest,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    doc=owned(db,user,document_id)
    chunks=retrieve_chunks(db,doc.id,payload.question)
    context="\n\n".join(f"[Page {c.page_number}]\n{c.content}" for c in chunks)
    answer=ai_or_error().ask(context,payload.question)
    session=db.scalar(select(ChatSession).where(ChatSession.user_id==user.id,ChatSession.document_id==doc.id).order_by(ChatSession.updated_at.desc()))
    if not session:
        session=ChatSession(user_id=user.id,document_id=doc.id); db.add(session); db.flush()
    pages=sorted({c.page_number for c in chunks})
    db.add(ChatMessage(session_id=session.id,role="user",content=payload.question,source_pages=",".join(map(str,pages))))
    db.add(ChatMessage(session_id=session.id,role="assistant",content=answer,source_pages=",".join(map(str,pages))))
    db.commit()
    sources=[Source(page=c.page_number,snippet=c.content[:500]) for c in chunks]
    return AskResponse(answer=answer,sources=sources)
