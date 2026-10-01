from pathlib import Path
import fitz
from fastapi import UploadFile, HTTPException, status
from app.core.config import get_settings

class PDFProcessingError(Exception): pass

async def save_and_extract_pdf(upload: UploadFile, destination: Path) -> tuple[int, str, list[tuple[int,str]]]:
    settings = get_settings()
    if Path(upload.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    if upload.content_type not in (None, "application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Invalid PDF MIME type")
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with destination.open("wb") as f:
        while True:
            data = await upload.read(1024 * 1024)
            if not data: break
            size += len(data)
            if size > settings.max_upload_size:
                f.close(); destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {settings.max_upload_size} bytes")
            f.write(data)
    try:
        doc = fitz.open(destination)
        if doc.is_encrypted:
            doc.close(); raise HTTPException(status_code=422, detail="Encrypted PDFs are not supported. Please upload an unencrypted PDF.")
        if doc.page_count == 0:
            doc.close(); raise HTTPException(status_code=422, detail="The PDF contains no pages")
        pages=[]
        for i,page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            pages.append((i, text))
        doc.close()
    except HTTPException: raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="The uploaded PDF is corrupt or cannot be read") from exc
    extracted = "\n\n".join(f"[Page {p}]\n{text}" for p,text in pages if text)
    if not extracted.strip():
        raise HTTPException(status_code=422, detail="No extractable text was found. This appears to be a scanned/image-only PDF; OCR is required before simplification or chat.")
    return size, extracted, pages
