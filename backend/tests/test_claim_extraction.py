import json

import pytest

from app import models
from app.db import Base, SessionLocal, engine
from app.services.article_service import ArticleService
from app.services.claim_extraction import parse_claim_extraction_json
from app.services.claim_service import ClaimService


def test_parse_claim_extraction_json_valid_payload():
    payload = {
        "claims": [
            {
                "claim_text": "OpenAI released a new model.",
                "claim_type": "observed_fact",
                "confidence": 0.91,
                "evidence": [
                    {
                        "evidence_text": "OpenAI released a new model today.",
                        "evidence_type": "reported_fact",
                    }
                ],
            }
        ]
    }

    result = parse_claim_extraction_json(json.dumps(payload))

    assert len(result.claims) == 1
    assert result.claims[0].claim_type == "observed_fact"


def test_parse_claim_extraction_json_invalid_payload_raises():
    invalid_payload = {"claims": [{"claim_type": "observed_fact", "evidence": []}]}

    with pytest.raises(ValueError):
        parse_claim_extraction_json(json.dumps(invalid_payload))


def test_claim_persistence_filters_non_factual_claim_types():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        article_service = ArticleService()
        claim_service = ClaimService()
        article_result = article_service.create_article_from_raw(
            db,
            source_name="S-claims",
            source_type="api",
            url="https://example.com/mixed-claims",
            title="Mixed claim types",
            raw_text="Authorities reported flooding. Analysts predict additional storms.",
        )
        article = db.query(models.Article).filter(models.Article.id == article_result.article_id).first()
        parsed = parse_claim_extraction_json(
            json.dumps(
                {
                    "claims": [
                        {
                            "claim_text": "Authorities reported flooding in three districts.",
                            "claim_type": "observed_fact",
                            "evidence": [
                                {
                                    "evidence_text": "Authorities reported flooding in three districts.",
                                    "evidence_type": "reported_fact",
                                }
                            ],
                        },
                        {
                            "claim_text": "Analysts predict heavier rain next week.",
                            "claim_type": "prediction",
                            "evidence": [
                                {
                                    "evidence_text": "Analysts predict heavier rain next week.",
                                    "evidence_type": "reported_fact",
                                }
                            ],
                        },
                        {
                            "claim_text": "Residents think the response has been too slow.",
                            "claim_type": "opinion",
                            "evidence": [
                                {
                                    "evidence_text": "Residents think the response has been too slow.",
                                    "evidence_type": "reported_fact",
                                }
                            ],
                        },
                    ]
                }
            )
        )

        result = claim_service.persist_extracted_claims(db, article=article, extraction_result=parsed)
        persisted_claims = db.query(models.Claim).filter(models.Claim.article_id == article.id).all()

        assert result.claims_created == 1
        assert len(persisted_claims) == 1
        assert persisted_claims[0].claim_type == "observed_fact"
    finally:
        db.close()
