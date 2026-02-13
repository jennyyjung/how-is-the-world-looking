from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app import models, schemas
from app.config.sources import SOURCE_REGISTRY
from app.db import Base, engine, get_db
from app.ingestion import IngestionRunner
from app.db import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="How Is The World Looking API")
ingestion_runner = IngestionRunner()


@app.get("/health", response_model=schemas.HealthResponse)
def health() -> schemas.HealthResponse:
    return schemas.HealthResponse()


@app.get("/sources")
def list_sources():
    return {"sources": [cfg.__dict__ for cfg in SOURCE_REGISTRY.values()]}


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


@app.post("/ingest/run", response_model=schemas.IngestionRunResponse)
def run_ingestion(payload: schemas.IngestionRunRequest, db: Session = Depends(get_db)) -> schemas.IngestionRunResponse:
    result = ingestion_runner.run(
        db=db,
        source_keys=payload.source_keys,
        limit_per_source=payload.limit_per_source,
    )
    return schemas.IngestionRunResponse(**result)
