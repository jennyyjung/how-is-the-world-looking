from fastapi.testclient import TestClient

from app.main import app


def test_create_article_endpoint():
    client = TestClient(app)
    payload = {
        "source_name": "Example News",
        "source_type": "wire",
        "url": "https://example.com/story-1",
        "title": "Test Story",
        "raw_text": "A factual sentence about an AI model release.",
    }
    response = client.post('/articles', json=payload)
    assert response.status_code == 200
    assert 'article_id' in response.json()
