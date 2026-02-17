from fastapi.testclient import TestClient

from app import models
from app.db import SessionLocal
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


def test_article_cleaned_text_is_full_text_and_dedupe_uses_stable_hash():
    client = TestClient(app)
    payload_a = {
        "source_name": "Example News",
        "source_type": "wire",
        "url": "https://example.com/story-cleaned-a",
        "title": "OpenAI Model Launch",
        "raw_text": "OpenAI launched a model today. Read more now!",
    }
    payload_b = {
        "source_name": "Another Outlet",
        "source_type": "wire",
        "url": "https://example.com/story-cleaned-b",
        "title": "OpenAI Model Launch Duplicate",
        "raw_text": "openai launched a model today read more now",
    }

    first = client.post('/articles', json=payload_a)
    second = client.post('/articles', json=payload_b)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["deduped"] is False
    assert second.json()["deduped"] is True
    assert first.json()["article_id"] == second.json()["article_id"]

    db = SessionLocal()
    try:
        article = db.query(models.Article).filter(models.Article.id == first.json()["article_id"]).first()
        assert article is not None
        assert article.cleaned_text == "openai launched a model today read more now"
    finally:
        db.close()
