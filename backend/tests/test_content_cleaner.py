from app.services.content_cleaner import ContentCleaner


def test_content_cleaner_removes_boilerplate_and_generates_hash():
    cleaner = ContentCleaner(keyword_limit=10)
    text = """
    <p>Subscribe to our newsletter!</p>
    OpenAI released a new reasoning model for enterprise developers.
    Read more at https://example.com/story.
    """

    result = cleaner.clean_for_keywords(text)

    assert "subscribe" not in result.cleaned_text
    assert "newsletter" not in result.cleaned_text
    assert "openai" in result.cleaned_text
    assert "reasoning" in result.cleaned_text
    assert len(result.content_hash) == 64


def test_content_cleaner_hash_stable_for_equivalent_text():
    cleaner = ContentCleaner()
    a = cleaner.clean_for_keywords("OpenAI launches GPT model. Read more!")
    b = cleaner.clean_for_keywords("openai launches gpt model read more")

    assert a.content_hash == b.content_hash
