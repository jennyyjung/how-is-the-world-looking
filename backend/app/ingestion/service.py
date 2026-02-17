from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

import httpx
from sqlalchemy.orm import Session

from app.config.sources import SOURCE_REGISTRY
from app.services.article_service import ArticleService


@dataclass
class NormalizedArticle:
    source_name: str
    source_type: str
    url: str
    title: str
    raw_text: str | None = None
    published_at: datetime | None = None


class SourceAdapter(Protocol):

    def fetch_items(self, limit: int) -> list[NormalizedArticle]:
        ...


class HackerNewsAdapter:
    source_key = "hacker_news"
    _BASE = "https://hacker-news.firebaseio.com/v0"

    def fetch_items(self, limit: int) -> list[NormalizedArticle]:
        with httpx.Client(timeout=15.0) as client:
            ids = client.get(f"{self._BASE}/topstories.json").raise_for_status().json()[:limit]
            items: list[NormalizedArticle] = []
            for item_id in ids:
                payload = client.get(f"{self._BASE}/item/{item_id}.json").raise_for_status().json()
                if payload.get("type") != "story" or not payload.get("url"):
                    continue
                published = None
                if payload.get("time"):
                    published = datetime.fromtimestamp(payload["time"], tz=timezone.utc)
                items.append(
                    NormalizedArticle(
                        source_name=SOURCE_REGISTRY[self.source_key].name,
                        source_type=SOURCE_REGISTRY[self.source_key].source_type,
                        url=payload["url"],
                        title=payload.get("title", "Untitled"),
                        raw_text=payload.get("text"),
                        published_at=published,
                    )
                )
            return items


class GitHubTrendingStarsAdapter:
    source_key = "github_trending_stars"
    _BASE = "https://api.github.com/search/repositories"

    def fetch_items(self, limit: int) -> list[NormalizedArticle]:
        since = (date.today() - timedelta(days=7)).isoformat()
        query = f"created:>{since}"
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        with httpx.Client(timeout=15.0, headers=headers) as client:
            response = client.get(
                self._BASE,
                params={
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": min(limit, 100),
                },
            )
            response.raise_for_status()
            payload = response.json()
            items: list[NormalizedArticle] = []
            for repo in payload.get("items", [])[:limit]:
                published = None
                if repo.get("created_at"):
                    published = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
                items.append(
                    NormalizedArticle(
                        source_name=SOURCE_REGISTRY[self.source_key].name,
                        source_type=SOURCE_REGISTRY[self.source_key].source_type,
                        url=repo["html_url"],
                        title=repo["full_name"],
                        raw_text=repo.get("description"),
                        published_at=published,
                    )
                )
            return items


class GoogleNewsAPIAdapter:
    source_key = "google_news_api"
    _BASE = "https://gnews.io/api/v4/top-headlines"

    def fetch_items(self, limit: int) -> list[NormalizedArticle]:
        api_key = os.getenv("GOOGLE_NEWS_API_KEY")
        if not api_key:
            return []

        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                self._BASE,
                params={
                    "token": api_key,
                    "topic": "technology",
                    "lang": "en",
                    "max": min(limit, 100),
                },
            )
            response.raise_for_status()
            payload = response.json()
            items: list[NormalizedArticle] = []
            for article in payload.get("articles", [])[:limit]:
                published = None
                if article.get("publishedAt"):
                    published = datetime.fromisoformat(article["publishedAt"].replace("Z", "+00:00"))
                raw_text = article.get("description") or article.get("content")
                items.append(
                    NormalizedArticle(
                        source_name=SOURCE_REGISTRY[self.source_key].name,
                        source_type=SOURCE_REGISTRY[self.source_key].source_type,
                        url=article["url"],
                        title=article.get("title", "Untitled"),
                        raw_text=raw_text,
                        published_at=published,
                    )
                )
            return items


class IngestionRunner:
    def __init__(self, article_service: ArticleService | None = None) -> None:
        self.adapters: dict[str, SourceAdapter] = {
            "hacker_news": HackerNewsAdapter(),
            "github_trending_stars": GitHubTrendingStarsAdapter(),
            "google_news_api": GoogleNewsAPIAdapter(),
        }
        self.article_service = article_service or ArticleService()

    def available_sources(self) -> list[str]:
        return list(self.adapters.keys())

    def run(self, db: Session, source_keys: list[str] | None = None, limit_per_source: int = 10) -> dict[str, Any]:
        selected = source_keys or self.available_sources()
        results: dict[str, Any] = {"ingested": 0, "skipped": 0, "sources": {}}

        for source_key in selected:
            adapter = self.adapters.get(source_key)
            if adapter is None:
                results["sources"][source_key] = {"error": "unknown_source"}
                continue

            fetched = adapter.fetch_items(limit_per_source)
            source_ingested = 0
            source_skipped = 0
            for item in fetched:
                upsert_result = self.article_service.create_article_from_raw(
                    db,
                    source_name=item.source_name,
                    source_type=item.source_type,
                    url=item.url,
                    title=item.title,
                    raw_text=item.raw_text,
                    published_at=item.published_at,
                )
                if upsert_result.deduped:
                    source_skipped += 1
                else:
                    source_ingested += 1

            results["ingested"] += source_ingested
            results["skipped"] += source_skipped
            results["sources"][source_key] = {
                "fetched": len(fetched),
                "ingested": source_ingested,
                "skipped": source_skipped,
            }
        return results
