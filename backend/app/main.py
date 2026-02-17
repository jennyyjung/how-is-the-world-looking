from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.config.sources import SOURCE_REGISTRY
from app.db import Base, engine, get_db
from app.ingestion import IngestionRunner
from app.services.article_service import ArticleService
from app.services.claim_extraction import parse_claim_extraction_json
from app.services.claim_service import ClaimService
from app.services.cluster_service import ClusterService

Base.metadata.create_all(bind=engine)

app = FastAPI(title="How Is The World Looking API")
ingestion_runner = IngestionRunner()
article_service = ArticleService()
claim_service = ClaimService()
cluster_service = ClusterService()


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


@app.post("/extract/claims", response_model=schemas.ClaimExtractionRunResponse)
def extract_claims(
    payload: schemas.ClaimExtractionRunRequest,
    db: Session = Depends(get_db),
) -> schemas.ClaimExtractionRunResponse:
    article = db.query(models.Article).filter(models.Article.id == payload.article_id).first()
    if article is None:
        raise HTTPException(status_code=404, detail="article_not_found")

    try:
        extraction_result = parse_claim_extraction_json(payload.model_output_json)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    persist_result = claim_service.persist_extracted_claims(
        db,
        article=article,
        extraction_result=extraction_result,
        extraction_model=payload.extraction_model,
        extraction_version=payload.extraction_version,
    )
    return schemas.ClaimExtractionRunResponse(
        claims_created=persist_result.claims_created,
        evidence_created=persist_result.evidence_created,
    )


@app.post("/clusters/build", response_model=schemas.ClusterBuildResponse)
def build_clusters(payload: schemas.ClusterBuildRequest, db: Session = Depends(get_db)) -> schemas.ClusterBuildResponse:
    result = cluster_service.build_clusters(
        db,
        lookback_hours=payload.lookback_hours,
        similarity_threshold=payload.similarity_threshold,
    )
    return schemas.ClusterBuildResponse(
        clusters_created=result.clusters_created,
        claims_clustered=result.claims_clustered,
        claims_scanned=result.claims_scanned,
    )
