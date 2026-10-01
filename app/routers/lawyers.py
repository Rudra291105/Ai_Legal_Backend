import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies.auth import get_current_lawyer
from app.models import LawyerDocument, User
from app.schemas.lawyer import LawyerDocumentCreate, LawyerDocumentUpdate, LawyerDocumentResponse, FinalizeResponse
from app.services.ai_service import AIService, AIConfigurationError

router=APIRouter(prefix="/api/lawyers/documents", tags=["Lawyer Documents"])

def own(db,lawyer,id):
    doc=db.scalar(select(LawyerDocument).where(LawyerDocument.id==id,LawyerDocument.lawyer_id==lawyer.id))
    if not doc: raise HTTPException(status_code=404,detail="Lawyer document not found")
    return doc

def response(d):
    return LawyerDocumentResponse(id=d.id,title=d.title,document_type=d.document_type,input_data=json.loads(d.input_data),generated_content=d.generated_content,status=d.status,created_at=d.created_at,updated_at=d.updated_at)

def ai():
    try:return AIService()
    except AIConfigurationError as e:raise HTTPException(status_code=503,detail=str(e))

@router.post("",response_model=LawyerDocumentResponse,status_code=201)
def create(payload:LawyerDocumentCreate,lawyer:User=Depends(get_current_lawyer),db:Session=Depends(get_db)):
    d=LawyerDocument(lawyer_id=lawyer.id,title=payload.title,document_type=payload.document_type,input_data=json.dumps(payload.input_data),status="DRAFT")
    db.add(d);db.commit();db.refresh(d);return response(d)

@router.get("",response_model=list[LawyerDocumentResponse])
def list_docs(lawyer:User=Depends(get_current_lawyer),db:Session=Depends(get_db)):
    return [response(d) for d in db.scalars(select(LawyerDocument).where(LawyerDocument.lawyer_id==lawyer.id).order_by(LawyerDocument.updated_at.desc())).all()]

@router.get("/{document_id}",response_model=LawyerDocumentResponse)
def get_doc(document_id:int,lawyer:User=Depends(get_current_lawyer),db:Session=Depends(get_db)):return response(own(db,lawyer,document_id))

@router.put("/{document_id}",response_model=LawyerDocumentResponse)
def update(document_id:int,payload:LawyerDocumentUpdate,lawyer:User=Depends(get_current_lawyer),db:Session=Depends(get_db)):
    d=own(db,lawyer,document_id)
    if payload.title is not None:d.title=payload.title
    if payload.document_type is not None:d.document_type=payload.document_type
    if payload.input_data is not None:d.input_data=json.dumps(payload.input_data)
    if payload.generated_content is not None:d.generated_content=payload.generated_content
    d.status="DRAFT" if d.status!="FINAL" else d.status
    db.commit();db.refresh(d);return response(d)

@router.delete("/{document_id}",status_code=204)
def delete(document_id:int,lawyer:User=Depends(get_current_lawyer),db:Session=Depends(get_db)):
    d=own(db,lawyer,document_id);db.delete(d);db.commit()

@router.post("/{document_id}/generate",response_model=LawyerDocumentResponse)
def generate(document_id:int,lawyer:User=Depends(get_current_lawyer),db:Session=Depends(get_db)):
    d=own(db,lawyer,document_id);d.generated_content=ai().generate_legal_draft(d.document_type,json.loads(d.input_data));d.status="GENERATED";db.commit();db.refresh(d);return response(d)

@router.post("/{document_id}/finalize",response_model=FinalizeResponse)
def finalize(document_id:int,lawyer:User=Depends(get_current_lawyer),db:Session=Depends(get_db)):
    d=own(db,lawyer,document_id)
    if not d.generated_content.strip():raise HTTPException(status_code=409,detail="Generate or write document content before finalizing")
    d.status="FINAL";db.commit();db.refresh(d);return FinalizeResponse(id=d.id,status=d.status,content=d.generated_content)
