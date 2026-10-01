from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.routers import auth, documents, lawyers, workspaces

settings=get_settings()
app=FastAPI(title="AI Legal Document Simplifier",version="1.0.0",description="Legal document explanation and lawyer drafting API.")
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_url],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.include_router(auth.router);app.include_router(documents.router);app.include_router(lawyers.router);app.include_router(workspaces.router)

@app.exception_handler(Exception)
async def unhandled(request:Request,exc:Exception):
    return JSONResponse(status_code=500,content={"detail":"Internal server error"})


@app.get("/",tags=["System"])
def root():return {"message":"Welcome to the AI Legal Document Simplifier API. Visit /docs for API documentation."}

@app.get("/health",tags=["System"])
def health():return {"status":"ok"}
