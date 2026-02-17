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


def test_reextract_cleans_relations_and_summary_citations_for_old_claim_ids():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        article_service = ArticleService()
        claim_service = ClaimService()

        created = article_service.create_article_from_raw(
            db,
            source_name="Example 2",
            source_type="api",
            url="https://example.com/a2",
            title="AI update",
            raw_text="Vendor increased AI chip output.",
        )
        article = db.query(models.Article).filter(models.Article.id == created.article_id).first()

        initial_output = {
            "claims": [
                {
                    "claim_text": "Vendor increased AI chip output.",
                    "claim_type": "observed_fact",
                    "evidence": [
                        {
                            "evidence_text": "Vendor increased AI chip output.",
                            "evidence_type": "reported_fact",
                        }
                    ],
                }
            ]
        }
        parsed_initial = parse_claim_extraction_json(json.dumps(initial_output))
        claim_service.persist_extracted_claims(db, article=article, extraction_result=parsed_initial)

        old_claim = db.query(models.Claim).filter(models.Claim.article_id == article.id).first()
        old_evidence = db.query(models.ClaimEvidence).filter(models.ClaimEvidence.claim_id == old_claim.id).first()

        db.add(
            models.ClaimRelation(
                left_claim_id=old_claim.id,
                right_claim_id=old_claim.id,
                relation_type="supports",
                score=1.0,
            )
        )
        summary = models.Summary(
            event_cluster_id=models.EventCluster(canonical_title="tmp").id,
            agreed_facts_json=json.dumps([old_claim.claim_text]),
            disputed_claims_json="[]",
            unknowns_json="[]",
            confidence_rationale="test",
            confidence_score=0.5,
        )
        cluster = models.EventCluster(canonical_title="tmp")
        db.add(cluster)
        db.flush()
        summary.event_cluster_id = cluster.id
        db.add(summary)
        db.flush()
        db.add(
            models.SummaryCitation(
                summary_id=summary.id,
                section="agreed_facts",
                bullet_index=0,
                claim_id=old_claim.id,
                evidence_id=old_evidence.id,
            )
        )
        db.commit()

        rerun_output = {
            "claims": [
                {
                    "claim_text": "Vendor reported stable AI chip output.",
                    "claim_type": "observed_fact",
                    "evidence": [
                        {
                            "evidence_text": "Vendor reported stable AI chip output.",
                            "evidence_type": "reported_fact",
                        }
                    ],
                }
            ]
        }
        parsed_rerun = parse_claim_extraction_json(json.dumps(rerun_output))
        claim_service.persist_extracted_claims(db, article=article, extraction_result=parsed_rerun)

        assert db.query(models.Claim).filter(models.Claim.id == old_claim.id).count() == 0
        assert (
            db.query(models.ClaimRelation)
            .filter(
                (models.ClaimRelation.left_claim_id == old_claim.id)
                | (models.ClaimRelation.right_claim_id == old_claim.id)
            )
            .count()
            == 0
        )
        assert db.query(models.SummaryCitation).filter(models.SummaryCitation.claim_id == old_claim.id).count() == 0
    finally:
        db.close()
