import json

from app import models
from app.db import Base, SessionLocal, engine
from app.services.article_service import ArticleService
from app.services.claim_extraction import parse_claim_extraction_json
from app.services.claim_service import ClaimService


def test_persist_extracted_claims_with_evidence():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        article_service = ArticleService()
        claim_service = ClaimService()

        created = article_service.create_article_from_raw(
            db,
            source_name="Example",
            source_type="api",
            url="https://example.com/a1",
            title="AI launch",
            raw_text="Vendor launched a new AI model.",
        )
        article = db.query(models.Article).filter(models.Article.id == created.article_id).first()

        output = {
            "claims": [
                {
                    "claim_text": "Vendor launched a new AI model.",
                    "claim_type": "observed_fact",
                    "confidence": 0.88,
                    "evidence": [
                        {
                            "evidence_text": "Vendor launched a new AI model.",
                            "evidence_type": "reported_fact",
                        }
                    ],
                }
            ]
        }
        parsed = parse_claim_extraction_json(json.dumps(output))
        persist_result = claim_service.persist_extracted_claims(
            db,
            article=article,
            extraction_result=parsed,
            extraction_model="test-model",
            extraction_version="v1",
        )

        assert persist_result.claims_created == 1
        assert persist_result.evidence_created == 1
        assert db.query(models.Claim).filter(models.Claim.article_id == article.id).count() == 1
        claim = db.query(models.Claim).filter(models.Claim.article_id == article.id).first()
        assert db.query(models.ClaimEvidence).filter(models.ClaimEvidence.claim_id == claim.id).count() == 1
    finally:
        db.close()
