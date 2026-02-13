from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="How Is The World Looking API")


@app.get("/health", response_model=schemas.HealthResponse)
def health() -> schemas.HealthResponse:
    return schemas.HealthResponse()


@app.post("/articles")
def create_article(payload: schemas.ArticleInput, db: Session = Depends(get_db)):
    source = db.query(models.Source).filter(models.Source.name == payload.source_name).first()
    if source is None:
        source = models.Source(name=payload.source_name, source_type=payload.source_type)
        db.add(source)
        db.flush()

    article = models.Article(
        source_id=source.id,
        url=payload.url,
        title=payload.title,
        cleaned_text=payload.cleaned_text,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return {"article_id": article.id}
