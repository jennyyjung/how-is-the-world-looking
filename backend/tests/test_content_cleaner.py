from app.services.content_cleaner import ContentCleaner


def test_content_cleaner_removes_boilerplate_and_generates_hash():
    cleaner = ContentCleaner(keyword_limit=10)
    text = """
    <p>Subscribe to our newsletter!</p>
    OpenAI released a new reasoning model for enterprise developers.
    Read more at https://example.com/story.
    """

    result = cleaner.clean_for_keywords(text)

    assert result.cleaned_text.startswith("subscribe to our newsletter")
    assert "openai released a new reasoning model for enterprise developers" in result.cleaned_text
    assert "https" not in result.cleaned_text
    assert "subscribe" not in result.keyword_text
    assert "newsletter" not in result.keyword_text
    assert "openai" in result.cleaned_text
    assert "reasoning" in result.keyword_text
    assert len(result.content_hash) == 64


def test_content_cleaner_keeps_full_sentence_text_separate_from_keyword_text():
    cleaner = ContentCleaner(keyword_limit=5)
    result = cleaner.clean_for_keywords("OpenAI launched a model today. Developers tested it in production.")

    assert result.cleaned_text == "openai launched a model today developers tested it in production"
    assert result.keyword_text == "developers launched model openai production"


def test_content_cleaner_hash_stable_for_equivalent_text():
    cleaner = ContentCleaner()
    a = cleaner.clean_for_keywords("OpenAI launches GPT model. Read more!")
    b = cleaner.clean_for_keywords("openai launches gpt model read more")

    assert a.content_hash == b.content_hash
