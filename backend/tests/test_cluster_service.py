from app.services.cluster_service import ClusterService


def test_jaccard_similarity_nonzero_for_overlap():
    service = ClusterService()
    score = service._jaccard({"openai", "model", "launch"}, {"openai", "model", "release"})
    assert score > 0


def test_tokens_normalize_and_filter_short_words():
    service = ClusterService()
    tokens = service._tokens("AI model by OpenAI in 2026")
    assert "model" in tokens
    assert "openai" in tokens
    assert "ai" not in tokens
