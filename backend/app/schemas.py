from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class ArticleInput(BaseModel):
    source_name: str
    source_type: str = "newspaper"
    url: str
    title: str
    raw_text: str | None = None


class IngestionRunRequest(BaseModel):
    source_keys: list[str] | None = None
    limit_per_source: int = Field(default=10, ge=1, le=100)


class IngestionRunResponse(BaseModel):
    ingested: int
    skipped: int
    sources: dict


class ClaimExtractionRunRequest(BaseModel):
    article_id: str
    model_output_json: str
    extraction_model: str | None = None
    extraction_version: str | None = None


class ClaimExtractionRunResponse(BaseModel):
    claims_created: int
    evidence_created: int


class ClusterBuildRequest(BaseModel):
    lookback_hours: int = Field(default=72, ge=1, le=720)
    similarity_threshold: float = Field(default=0.35, ge=0.0, le=1.0)


class ClusterBuildResponse(BaseModel):
    clusters_created: int
    claims_clustered: int
    claims_scanned: int
