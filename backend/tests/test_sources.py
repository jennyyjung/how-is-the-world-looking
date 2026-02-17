from app.config.sources import SOURCE_REGISTRY


def test_source_registry_contains_required_sources():
    assert "github_trending_stars" in SOURCE_REGISTRY
    assert "hacker_news" in SOURCE_REGISTRY
    assert "google_news_api" in SOURCE_REGISTRY
