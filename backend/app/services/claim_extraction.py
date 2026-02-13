from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError


FACTUAL_EXTRACTION_SYSTEM_PROMPT = """You are a factual claim extraction engine.
Extract only verifiable claims, and include direct evidence spans.
Return JSON only, strictly following the schema contract.
"""


CLAIM_SCHEMA_CONTRACT = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim_text": {"type": "string"},
                    "claim_type": {
                        "type": "string",
                        "enum": [
                            "observed_fact",
                            "attributed_statement",
                            "inference",
                            "prediction",
                            "opinion",
                        ],
                    },
                    "subject": {"type": ["string", "null"]},
                    "predicate": {"type": ["string", "null"]},
                    "object": {"type": ["string", "null"]},
                    "occurred_at": {"type": ["string", "null"]},
                    "location_text": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "uncertainty_reason": {"type": ["string", "null"]},
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "evidence_text": {"type": "string"},
                                "start_char": {"type": ["integer", "null"]},
                                "end_char": {"type": ["integer", "null"]},
                                "evidence_type": {
                                    "type": "string",
                                    "enum": ["direct_quote", "reported_fact", "document_reference"],
                                },
                            },
                            "required": ["evidence_text", "evidence_type"],
                        },
                    },
                },
                "required": ["claim_text", "claim_type", "evidence"],
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_text: str
    start_char: int | None = None
    end_char: int | None = None
    evidence_type: str = Field(pattern="^(direct_quote|reported_fact|document_reference)$")


class ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: str
    claim_type: str = Field(pattern="^(observed_fact|attributed_statement|inference|prediction|opinion)$")
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    occurred_at: str | None = None
    location_text: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty_reason: str | None = None
    evidence: list[EvidenceItem] = Field(min_length=1)


class ClaimExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ExtractedClaim]


@dataclass
class ExtractionPrompt:
    system_prompt: str
    user_prompt: str


def build_claim_extraction_prompt(source_name: str, title: str, cleaned_text: str) -> ExtractionPrompt:
    user_prompt = (
        f"Source: {source_name}\n"
        f"Title: {title}\n\n"
        "Article text:\n"
        f"{cleaned_text}\n\n"
        "Extract factual claims following the schema contract."
    )
    return ExtractionPrompt(system_prompt=FACTUAL_EXTRACTION_SYSTEM_PROMPT, user_prompt=user_prompt)


def parse_claim_extraction_json(model_output_json: str) -> ClaimExtractionResult:
    try:
        payload = json.loads(model_output_json)
        return ClaimExtractionResult.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Invalid claim extraction output: {exc}") from exc
