from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.services.content_cleaner import ContentCleaner


@dataclass
class ArticleUpsertResult:
    article_id: str
    deduped: bool


class ArticleService:
    def __init__(self, cleaner: ContentCleaner | None = None) -> None:
        self.cleaner = cleaner or ContentCleaner()

    def get_or_create_source(self, db: Session, source_name: str, source_type: str) -> models.Source:
        source = db.query(models.Source).filter(models.Source.name == source_name).first()
        if source is not None:
            return source

        source = models.Source(name=source_name, source_type=source_type)
        db.add(source)
        db.flush()
        return source

    def create_article_from_raw(
        self,
        db: Session,
        *,
        source_name: str,
        source_type: str,
        url: str,
        title: str,
        raw_text: str | None,
        published_at: datetime | None = None,
    ) -> ArticleUpsertResult:
        cleaned = self.cleaner.clean_for_keywords(raw_text or title)
        dedupe_hash = cleaned.content_hash
        existing = db.query(models.Article).filter(models.Article.content_hash == dedupe_hash).first()
        if existing:
            return ArticleUpsertResult(article_id=existing.id, deduped=True)

        source = self.get_or_create_source(db, source_name=source_name, source_type=source_type)
        article = models.Article(
            source_id=source.id,
            url=url,
            title=title,
            cleaned_text=cleaned.cleaned_text,
            content_hash=dedupe_hash,
            published_at=published_at,
        )
        db.add(article)
        try:
            db.commit()
            db.refresh(article)
            return ArticleUpsertResult(article_id=article.id, deduped=False)
        except IntegrityError:
            db.rollback()
            existing_by_url = db.query(models.Article).filter(models.Article.url == url).first()
            if existing_by_url:
                return ArticleUpsertResult(article_id=existing_by_url.id, deduped=True)
            raise
