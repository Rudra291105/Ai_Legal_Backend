from app.services.chunking_service import chunk_pages, normalize

def test_normalize_whitespace():
    assert normalize(' hello   world\n\n\n next ') == 'hello world\n\nnext'

def test_chunking_preserves_pages_and_indexes():
    chunks=chunk_pages([(1,'Paragraph one.\n\nParagraph two.'),(2,'Paragraph three.')],max_chars=100)
    assert [c['page_number'] for c in chunks]==[1,2]
    assert [c['chunk_index'] for c in chunks]==list(range(len(chunks)))
    assert all('content' in c and c['content'] for c in chunks)
