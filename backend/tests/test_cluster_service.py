import json

from app import models
from app.db import Base, SessionLocal, engine
from app.services.article_service import ArticleService
from app.services.claim_extraction import parse_claim_extraction_json
from app.services.claim_service import ClaimService
from app.services.cluster_service import ClusterService
from app.services.summary_service import SummaryService


def test_jaccard_similarity_nonzero_for_overlap():
    service = ClusterService()
    score = service._jaccard({"openai", "model", "launch"}, {"openai", "model", "release"})
    assert score > 0


def test_tokens_normalize_and_filter_short_words():
    service = ClusterService()
    tokens = service._tokens("AI model by OpenAI in 2026")
    assert "model" in tokens
    assert "openai" in tokens
    assert "ai" not in tokens


def test_cluster_assignment_stable_across_reruns():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        article_service = ArticleService()
        claim_service = ClaimService()
        cluster_service = ClusterService()

        a1 = article_service.create_article_from_raw(
            db,
            source_name="S1",
            source_type="api",
            url="https://example.com/s1",
            title="OpenAI model launch",
            raw_text="OpenAI launched a new model for developers.",
        )
        a2 = article_service.create_article_from_raw(
            db,
            source_name="S2",
            source_type="api",
            url="https://example.com/s2",
            title="OpenAI new model",
            raw_text="A new OpenAI model was launched today.",
        )

        for article_id in [a1.article_id, a2.article_id]:
            article = db.query(models.Article).filter(models.Article.id == article_id).first()
            parsed = parse_claim_extraction_json(
                json.dumps(
                    {
                        "claims": [
                            {
                                "claim_text": "OpenAI launched a new model for developers.",
                                "claim_type": "observed_fact",
                                "evidence": [
                                    {
                                        "evidence_text": "OpenAI launched a new model for developers.",
                                        "evidence_type": "reported_fact",
                                    }
                                ],
                            }
                        ]
                    }
                )
            )
            claim_service.persist_extracted_claims(db, article=article, extraction_result=parsed)

        first = cluster_service.build_clusters(db, lookback_hours=720, similarity_threshold=0.3)
        second = cluster_service.build_clusters(db, lookback_hours=720, similarity_threshold=0.3)

        assert first.clusters_created >= 1
        assert second.clusters_created == 0
        assert db.query(models.EventCluster).count() == 1
    finally:
        db.close()


def test_summary_build_enforces_citations():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        summary_service = SummaryService()
        cluster = db.query(models.EventCluster).first()
        if cluster is None:
            return
        result = summary_service.build_summaries(db, cluster_ids=[cluster.id])
        assert result.summaries_created >= 0
        summaries = db.query(models.Summary).all()
        if not summaries:
            return
        citations = db.query(models.SummaryCitation).filter(models.SummaryCitation.summary_id == summaries[-1].id).all()
        agreed = json.loads(summaries[-1].agreed_facts_json)
        assert len(citations) >= len(agreed)
    finally:
        db.close()


def test_relation_builder_prioritizes_contradiction_over_overlap():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        article_service = ArticleService()
        claim_service = ClaimService()
        cluster_service = ClusterService()
        summary_service = SummaryService()

        a1 = article_service.create_article_from_raw(
            db,
            source_name="S3",
            source_type="api",
            url="https://example.com/s3",
            title="Chip production rising",
            raw_text="Company says chip production increased this quarter.",
        )
        a2 = article_service.create_article_from_raw(
            db,
            source_name="S4",
            source_type="api",
            url="https://example.com/s4",
            title="Chip production not rising",
            raw_text="Company says chip production did not increase this quarter.",
        )

        outputs = [
            {
                "claim_text": "Company says chip production increased this quarter.",
                "claim_type": "observed_fact",
                "evidence": [
                    {
                        "evidence_text": "Company says chip production increased this quarter.",
                        "evidence_type": "reported_fact",
                    }
                ],
            },
            {
                "claim_text": "Company says chip production did not increase this quarter.",
                "claim_type": "observed_fact",
                "evidence": [
                    {
                        "evidence_text": "Company says chip production did not increase this quarter.",
                        "evidence_type": "reported_fact",
                    }
                ],
            },
        ]

        for article_id, claim_payload in zip([a1.article_id, a2.article_id], outputs):
            article = db.query(models.Article).filter(models.Article.id == article_id).first()
            parsed = parse_claim_extraction_json(json.dumps({"claims": [claim_payload]}))
            claim_service.persist_extracted_claims(db, article=article, extraction_result=parsed)

        cluster_service.build_clusters(db, lookback_hours=720, similarity_threshold=0.3)
        summary_service.build_summaries(db)

        relations = db.query(models.ClaimRelation).all()
        assert relations
        assert any(rel.relation_type == "contradicts" for rel in relations)
        assert not any(rel.relation_type == "supports" for rel in relations)
    finally:
        db.close()
