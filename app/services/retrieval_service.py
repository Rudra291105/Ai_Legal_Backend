import re
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.models import DocumentChunk

def retrieve_chunks(db: Session, document_id: int, question: str, limit: int = 6) -> list[DocumentChunk]:
    chunks=list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id==document_id)).all())
    terms={t.lower() for t in re.findall(r"[A-Za-z0-9]{3,}", question)}
    scored=[]
    for c in chunks:
        words=re.findall(r"[A-Za-z0-9]{3,}", c.content.lower())
        counts={w:words.count(w) for w in terms}
        score=sum(counts.values())
        if any(term in c.content.lower() for term in terms): score += 0.5
        scored.append((score,c))
    scored.sort(key=lambda x:x[0], reverse=True)
    return [c for score,c in scored[:limit] if score>0] or chunks[:limit]


# ---------------------------------------------------------------------------
# Workspace (multi-document) retrieval
# ---------------------------------------------------------------------------
# Keep this function's signature stable: it is the single seam where a future
# pgvector / embedding search can replace the lexical ranking below.
from dataclasses import dataclass
import math
from app.models import Document

_STOPWORDS = {
    "the","and","for","are","was","were","has","have","had","how","what","when","where","which","who","whom",
    "why","does","did","not","but","with","that","this","these","those","from","into","about","than","then",
    "there","their","them","they","you","your","can","could","would","should","will","shall","its","his","her",
    "also","any","all","some","over","under","between","through","during","explain","tell","give","show","describe",
    "is","in","of","to","on","at","by","an","as","be","or","it","do","if","me","my","we","us","a",
}


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    document_name: str
    page_number: int
    content: str
    score: float


def _stem(word: str) -> str:
    if word.isdigit():
        return word
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ied", "ed", "es", "ly", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _query_terms(question: str, max_terms: int = 12) -> list[str]:
    seen: list[str] = []
    for w in re.findall(r"[A-Za-z0-9]+", question.lower()):
        if w in _STOPWORDS or (len(w) < 3 and not w.isdigit()):
            continue
        s = _stem(w)
        if s not in seen:
            seen.append(s)
    return seen[:max_terms]


def _tf(stem: str, tokens: list[str]) -> int:
    if stem.isdigit():
        return sum(1 for t in tokens if t == stem)
    return sum(1 for t in tokens if t.startswith(stem))


def retrieve_workspace_chunks(
    db: Session,
    workspace_id: int,
    question: str,
    limit: int = 8,
    max_per_document: int = 4,
    candidate_limit: int = 1500,
) -> list[RetrievedChunk]:
    """Return the chunks of ONE workspace most relevant to `question`.

    Only chunks of documents whose `workspace_id` matches are ever read, so
    unrelated workspaces/documents can never reach the AI. Returns an empty
    list when nothing matches (callers must not fall back to arbitrary chunks).

    Ranking: SQL prefilter (ILIKE on query stems) followed by BM25-style
    scoring plus a phrase boost, with a per-document cap so a single long PDF
    cannot crowd out the others.
    """
    terms = _query_terms(question)
    if not terms:
        return []

    rows = db.execute(
        select(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.page_number,
               DocumentChunk.content, Document.original_filename)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.workspace_id == workspace_id)
        .where(or_(*[DocumentChunk.content.ilike(f"%{t}%") for t in terms]))
        .limit(candidate_limit)
    ).all()
    if not rows:
        return []

    tokenised = [re.findall(r"[a-z0-9]+", r.content.lower()) for r in rows]
    n = len(rows)
    avg_len = sum(len(t) for t in tokenised) / n or 1
    df = {t: sum(1 for toks in tokenised if _tf(t, toks) > 0) for t in terms}
    idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in terms}
    bigrams = [f"{a} {b}" for a, b in zip(terms, terms[1:])]
    k1, b = 1.5, 0.75

    scored: list[RetrievedChunk] = []
    for r, toks in zip(rows, tokenised):
        score = 0.0
        for t in terms:
            tf = _tf(t, toks)
            if tf:
                score += idf[t] * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * len(toks) / avg_len))
        if score <= 0:
            continue
        lowered = " ".join(toks)
        score += 0.5 * sum(1 for bg in bigrams if bg in lowered)
        scored.append(RetrievedChunk(r.id, r.document_id, r.original_filename, r.page_number, r.content, score))

    scored.sort(key=lambda c: c.score, reverse=True)
    selected: list[RetrievedChunk] = []
    per_doc: dict[int, int] = {}
    for c in scored:
        if len(selected) >= limit:
            break
        if per_doc.get(c.document_id, 0) < max_per_document:
            selected.append(c)
            per_doc[c.document_id] = per_doc.get(c.document_id, 0) + 1
    # Backfill (e.g. single-document workspace) once the per-document cap has been honoured.
    if len(selected) < limit:
        chosen = {c.chunk_id for c in selected}
        for c in scored:
            if len(selected) >= limit:
                break
            if c.chunk_id not in chosen:
                selected.append(c)
    return selected
