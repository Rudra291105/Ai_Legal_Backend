from pathlib import Path
from uuid import uuid4
from app.core.config import get_settings

def unique_pdf_path() -> tuple[str, Path]:
    settings=get_settings(); root=Path(settings.upload_dir); root.mkdir(parents=True,exist_ok=True)
    name=f"{uuid4().hex}.pdf"
    return name, root/name
