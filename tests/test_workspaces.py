import os, tempfile
_tmp = tempfile.mkdtemp()
os.environ['DATABASE_URL'] = f'sqlite:///{_tmp}/ws.db'
os.environ['JWT_SECRET_KEY'] = 'test-secret-long-enough'
os.environ['UPLOAD_DIR'] = f'{_tmp}/uploads'
os.environ['GEMINI_API_KEY'] = 'fake'

import fitz, pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.core.database import Base, get_db
from app.main import app
from app.core.config import get_settings
get_settings().upload_dir = os.environ['UPLOAD_DIR']  # settings may already be cached by another test module
from app.services import ai_service
from app.routers import workspaces as ws_router

engine = create_engine(os.environ['DATABASE_URL'], connect_args={'check_same_thread': False})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


def override_db():
    db = Session()
    try: yield db
    finally: db.close()


app.dependency_overrides[get_db] = override_db
client = TestClient(app)
captured = {}


class FakeAI:
    def ask_workspace(self, excerpts, question):
        captured['excerpts'] = excerpts
        return {"answer": "Fake answer", "found": True, "cited": [1]}


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    monkeypatch.setattr(ws_router, 'AIService', FakeAI)
    captured.clear()


def pdf_bytes(pages):
    d = fitz.open()
    for t in pages:
        d.new_page().insert_text((72, 72), t)
    b = d.tobytes(); d.close(); return b


def signup(email):
    r = client.post('/api/auth/signup', json={'full_name': 'Tester', 'email': email, 'password': 'password123', 'role': 'USER'})
    return {'Authorization': f"Bearer {r.json()['access_token']}"}


def test_full_flow_and_isolation():
    h = signup('a@example.com'); h2 = signup('b@example.com')
    r = client.post('/api/workspaces', json={'name': 'Constitutional Law'}, headers=h)
    assert r.status_code == 201; wid = r.json()['id']

    files = [('files', ('ManekaGandhi.pdf', pdf_bytes(['Intro page', 'Article 21 procedure established by law must be fair just and reasonable']), 'application/pdf')),
             ('files', ('Contracts.pdf', pdf_bytes(['Offer and acceptance form a contract']), 'application/pdf')),
             ('files', ('bad.txt', b'nope', 'text/plain'))]
    r = client.post(f'/api/workspaces/{wid}/documents', files=files, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body['uploaded']) == 2 and len(body['failed']) == 1 and body['failed'][0]['filename'] == 'bad.txt'

    # duplicate rejected; all-failed gives 422
    r = client.post(f'/api/workspaces/{wid}/documents', files=[files[0]], headers=h)
    assert r.status_code == 422 and 'already' in r.json()['failed'][0]['detail']

    assert client.get(f'/api/workspaces/{wid}', headers=h).json()['document_count'] == 2
    assert client.get('/api/workspaces', headers=h).json()[0]['document_count'] == 2
    # existing "My documents" list is unaffected by workspace docs
    assert client.get('/api/documents', headers=h).json() == []

    # chat: only relevant chunk is sent, sources carry document name + page
    r = client.post(f'/api/workspaces/{wid}/chat', json={'question': 'How has Article 21 evolved?'}, headers=h)
    assert r.status_code == 200, r.text
    assert len(captured['excerpts']) == 1
    assert 'Contract' not in captured['excerpts'][0][3]
    src = r.json()['sources']
    assert src == [{'document_id': src[0]['document_id'], 'document_name': 'ManekaGandhi.pdf', 'page': 2, 'snippet': src[0]['snippet']}]

    # irrelevant question: no Gemini call, no sources
    captured.clear()
    r = client.post(f'/api/workspaces/{wid}/chat', json={'question': 'photosynthesis chlorophyll'}, headers=h)
    assert r.json()['sources'] == [] and not captured

    # another user cannot see or touch it
    assert client.get(f'/api/workspaces/{wid}', headers=h2).status_code == 404
    assert client.post(f'/api/workspaces/{wid}/chat', json={'question': 'Article 21'}, headers=h2).status_code == 404
    assert client.get('/api/workspaces', headers=h2).json() == []

    # delete a document, then the workspace (files removed from disk)
    docs = client.get(f'/api/workspaces/{wid}/documents', headers=h).json()
    assert client.delete(f'/api/workspaces/{wid}/documents/{docs[0]["id"]}', headers=h).status_code == 204
    assert client.delete(f'/api/workspaces/{wid}/documents/{docs[0]["id"]}', headers=h).status_code == 404
    assert client.delete(f'/api/workspaces/{wid}', headers=h).status_code == 204
    assert client.get(f'/api/workspaces/{wid}', headers=h).status_code == 404
    assert os.listdir(os.environ['UPLOAD_DIR']) == []


def test_chunks_keep_document_and_page():
    from app.models import DocumentChunk
    h = signup('c@example.com')
    wid = client.post('/api/workspaces', json={'name': 'W'}, headers=h).json()['id']
    client.post(f'/api/workspaces/{wid}/documents', headers=h,
                files=[('files', ('x.pdf', pdf_bytes(['page one text', 'page two text']), 'application/pdf'))])
    with Session() as db:
        rows = db.query(DocumentChunk).all()
        assert {r.page_number for r in rows if 'two' in r.content} == {2}
        assert all(r.document_id for r in rows)


def test_not_found_flag_hides_sources(monkeypatch):
    class NF:
        def ask_workspace(self, e, q): return {"answer": "Not in docs", "found": False, "cited": []}
    monkeypatch.setattr(ws_router, 'AIService', NF)
    h = signup('d@example.com')
    wid = client.post('/api/workspaces', json={'name': 'W'}, headers=h).json()['id']
    client.post(f'/api/workspaces/{wid}/documents', headers=h,
                files=[('files', ('y.pdf', pdf_bytes(['liberty and dignity']), 'application/pdf'))])
    r = client.post(f'/api/workspaces/{wid}/chat', json={'question': 'liberty'}, headers=h)
    assert r.json() == {'answer': 'Not in docs', 'sources': []}


def test_empty_workspace_chat_rejected():
    h = signup('e@example.com')
    wid = client.post('/api/workspaces', json={'name': 'Empty'}, headers=h).json()['id']
    assert client.post(f'/api/workspaces/{wid}/chat', json={'question': 'anything'}, headers=h).status_code == 409
