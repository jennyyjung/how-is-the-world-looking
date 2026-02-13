from __future__ import annotations

import hashlib
import html
import re
from collections import Counter
from dataclasses import dataclass


STOPWORDS = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with", "from", "by", "at",
    "is", "are", "was", "were", "be", "been", "being", "that", "this", "it", "as", "its", "into",
    "about", "after", "before", "over", "under", "than", "then", "but", "if", "not", "no", "yes",
    "you", "your", "we", "our", "they", "their", "he", "she", "his", "her", "them", "us", "i",
}

BOILERPLATE_WORDS = {
    "subscribe", "newsletter", "cookies", "privacy", "advertisement", "sponsored", "click", "read", "more",
    "share", "login", "sign", "policy", "terms",
}


@dataclass
class CleanedContent:
    cleaned_text: str
    content_hash: str


class ContentCleaner:
    def __init__(self, keyword_limit: int = 25) -> None:
        self.keyword_limit = keyword_limit

    def clean_for_keywords(self, text: str | None) -> CleanedContent:
        if not text:
            return CleanedContent(cleaned_text="", content_hash=self.hash_text(""))

        normalized = self._normalize(text)
        tokens = self._tokenize(normalized)
        filtered_tokens = [
            token
            for token in tokens
            if token not in STOPWORDS and token not in BOILERPLATE_WORDS and len(token) > 2
        ]
        counts = Counter(filtered_tokens)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        keywords = [token for token, _ in ranked[: self.keyword_limit]]
        cleaned_text = " ".join(keywords)
        return CleanedContent(cleaned_text=cleaned_text, content_hash=self.hash_text(cleaned_text))

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize(text: str) -> str:
        unescaped = html.unescape(text)
        no_html = re.sub(r"<[^>]+>", " ", unescaped)
        no_urls = re.sub(r"https?://\S+", " ", no_html)
        alnum = re.sub(r"[^a-zA-Z0-9\s]", " ", no_urls)
        collapsed = re.sub(r"\s+", " ", alnum)
        return collapsed.strip().lower()

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        if not text:
            return []
        return text.split(" ")
