import re

def normalize(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def chunk_pages(pages: list[tuple[int,str]], max_chars: int = 3500, overlap: int = 300) -> list[dict]:
    chunks=[]; idx=0
    for page_number, raw in pages:
        text=normalize(raw)
        if not text: continue
        paragraphs=[p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        current=""
        for para in paragraphs:
            candidate=(current+"\n\n"+para).strip() if current else para
            if len(candidate)<=max_chars:
                current=candidate
            else:
                if current:
                    chunks.append({"chunk_index":idx,"page_number":page_number,"content":current}); idx+=1
                tail=current[-overlap:] if overlap and current else ""
                current=(tail+"\n\n"+para).strip()
                while len(current)>max_chars:
                    cut=current.rfind(" ",0,max_chars)
                    cut=max(cut, max_chars)
                    chunks.append({"chunk_index":idx,"page_number":page_number,"content":current[:cut].strip()}); idx+=1
                    current=current[max(0,cut-overlap):].strip()
        if current:
            chunks.append({"chunk_index":idx,"page_number":page_number,"content":current}); idx+=1
    return chunks
