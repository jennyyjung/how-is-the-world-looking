from dataclasses import asdict

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app import schemas
from app.config.sources import SOURCE_REGISTRY
from app.db import Base, engine, get_db
from app.ingestion import IngestionRunner
from app.services.article_service import ArticleService

Base.metadata.create_all(bind=engine)

app = FastAPI(title="How Is The World Looking API")
ingestion_runner = IngestionRunner()
article_service = ArticleService()


@app.get("/health", response_model=schemas.HealthResponse)
def health() -> schemas.HealthResponse:
    return schemas.HealthResponse()


@app.get("/sources")
def list_sources():
    return {"sources": [asdict(cfg) for cfg in SOURCE_REGISTRY.values()]}


@app.post("/articles")
def create_article(payload: schemas.ArticleInput, db: Session = Depends(get_db)):
    upsert_result = article_service.create_article_from_raw(
        db,
        source_name=payload.source_name,
        source_type=payload.source_type,
        url=payload.url,
        title=payload.title,
        raw_text=payload.raw_text,
    )
    return {"article_id": upsert_result.article_id, "deduped": upsert_result.deduped}


@app.post("/ingest/run", response_model=schemas.IngestionRunResponse)
def run_ingestion(payload: schemas.IngestionRunRequest, db: Session = Depends(get_db)) -> schemas.IngestionRunResponse:
    result = ingestion_runner.run(
        db=db,
        source_keys=payload.source_keys,
        limit_per_source=payload.limit_per_source,
    )
    return schemas.IngestionRunResponse(**result)
