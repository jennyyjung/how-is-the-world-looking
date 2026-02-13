from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class ClaimInput(BaseModel):
    claim_text: str
    claim_type: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ArticleInput(BaseModel):
    source_name: str
    source_type: str = "newspaper"
    url: str
    title: str
    cleaned_text: str | None = None
