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

        article_ids = [a1.article_id, a2.article_id]
        claim_ids = [
            row[0]
            for row in db.query(models.Claim.id).filter(models.Claim.article_id.in_(article_ids)).all()
        ]
        relations = (
            db.query(models.ClaimRelation)
            .filter(models.ClaimRelation.left_claim_id.in_(claim_ids))
            .filter(models.ClaimRelation.right_claim_id.in_(claim_ids))
            .all()
        )
        assert relations
        assert any(rel.relation_type == "contradicts" for rel in relations)
        assert not any(rel.relation_type == "supports" for rel in relations)
    finally:
        db.close()


def test_summary_ignores_opinions_and_predictions_in_mixed_claim_types():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        article_service = ArticleService()
        claim_service = ClaimService()
        cluster_service = ClusterService()
        summary_service = SummaryService()

        article_a = article_service.create_article_from_raw(
            db,
            source_name="S5",
            source_type="api",
            url="https://example.com/s5",
            title="Bridge closure confirmed",
            raw_text="Officials confirmed the bridge was closed."
        )
        article_b = article_service.create_article_from_raw(
            db,
            source_name="S6",
            source_type="api",
            url="https://example.com/s6",
            title="Bridge closure denied",
            raw_text="Officials said the bridge was not closed."
        )

        claims_by_article = {
            article_a.article_id: [
                {
                    "claim_text": "Officials confirmed the bridge was closed after inspection.",
                    "claim_type": "observed_fact",
                    "evidence": [
                        {
                            "evidence_text": "Officials confirmed the bridge was closed after inspection.",
                            "evidence_type": "reported_fact",
                        }
                    ],
                },
                {
                    "claim_text": "Residents believe this closure will last for months.",
                    "claim_type": "opinion",
                    "evidence": [
                        {
                            "evidence_text": "Residents believe this closure will last for months.",
                            "evidence_type": "reported_fact",
                        }
                    ],
                },
            ],
            article_b.article_id: [
                {
                    "claim_text": "Officials confirmed the bridge was not closed after inspection.",
                    "claim_type": "attributed_statement",
                    "evidence": [
                        {
                            "evidence_text": "Officials confirmed the bridge was not closed after inspection.",
                            "evidence_type": "reported_fact",
                        }
                    ],
                },
                {
                    "claim_text": "Forecasters predict closures could spread next month.",
                    "claim_type": "prediction",
                    "evidence": [
                        {
                            "evidence_text": "Forecasters predict closures could spread next month.",
                            "evidence_type": "reported_fact",
                        }
                    ],
                },
            ],
        }

        for article_id, claim_payloads in claims_by_article.items():
            article = db.query(models.Article).filter(models.Article.id == article_id).first()
            parsed = parse_claim_extraction_json(json.dumps({"claims": claim_payloads}))
            claim_service.persist_extracted_claims(db, article=article, extraction_result=parsed)

        cluster_service.build_clusters(db, lookback_hours=720, similarity_threshold=0.3)
        summary_service.build_summaries(db)

        latest_summary = db.query(models.Summary).order_by(models.Summary.created_at.desc()).first()
        assert latest_summary is not None

        agreed = json.loads(latest_summary.agreed_facts_json)
        disputed = json.loads(latest_summary.disputed_claims_json)

        non_factual_claims = {
            "Residents believe this closure will last for months.",
            "Forecasters predict closures could spread next month.",
        }

        assert non_factual_claims.isdisjoint(set(agreed))
        assert non_factual_claims.isdisjoint(set(disputed))
    finally:
        db.close()


def test_relation_builder_marks_conflicting_numbers_as_contradiction():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        article_service = ArticleService()
        summary_service = SummaryService()

        article_a = article_service.create_article_from_raw(
            db,
            source_name="S7",
            source_type="api",
            url="https://example.com/s7",
            title="Factory output claim A",
            raw_text="Company says factory output increased by 40% this quarter.",
        )
        article_b = article_service.create_article_from_raw(
            db,
            source_name="S8",
            source_type="api",
            url="https://example.com/s8",
            title="Factory output claim B",
            raw_text="Company says factory output increased by 25% this quarter.",
        )

        claim_a = models.Claim(
            article_id=article_a.article_id,
            claim_text="Company says factory output increased by 40% this quarter.",
            claim_type="observed_fact",
        )
        claim_b = models.Claim(
            article_id=article_b.article_id,
            claim_text="Company says factory output increased by 25% this quarter.",
            claim_type="observed_fact",
        )
        db.add_all([claim_a, claim_b])
        db.flush()

        created = summary_service._build_relations(db, [claim_a, claim_b])

        relations = (
            db.query(models.ClaimRelation)
            .filter(models.ClaimRelation.left_claim_id.in_([claim_a.id, claim_b.id]))
            .filter(models.ClaimRelation.right_claim_id.in_([claim_a.id, claim_b.id]))
            .all()
        )
        assert created == 1
        assert relations
        assert relations[0].relation_type == "contradicts"
    finally:
        db.close()


def test_relation_builder_marks_paraphrases_as_supports():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        article_service = ArticleService()
        summary_service = SummaryService()

        article_a = article_service.create_article_from_raw(
            db,
            source_name="S9",
            source_type="api",
            url="https://example.com/s9",
            title="Transit disruption headline A",
            raw_text="City officials confirmed the subway line reopened today.",
        )
        article_b = article_service.create_article_from_raw(
            db,
            source_name="S10",
            source_type="api",
            url="https://example.com/s10",
            title="Transit disruption headline B",
            raw_text="Officials said the city subway line reopened today.",
        )

        claim_a = models.Claim(
            article_id=article_a.article_id,
            claim_text="City officials confirmed the subway line reopened today.",
            claim_type="observed_fact",
        )
        claim_b = models.Claim(
            article_id=article_b.article_id,
            claim_text="Officials said the city subway line reopened today.",
            claim_type="observed_fact",
        )
        db.add_all([claim_a, claim_b])
        db.flush()

        created = summary_service._build_relations(db, [claim_a, claim_b])

        relations = (
            db.query(models.ClaimRelation)
            .filter(models.ClaimRelation.left_claim_id.in_([claim_a.id, claim_b.id]))
            .filter(models.ClaimRelation.right_claim_id.in_([claim_a.id, claim_b.id]))
            .all()
        )
        assert created == 1
        assert relations
        assert relations[0].relation_type == "supports"
    finally:
        db.close()


def test_relation_builder_skips_low_overlap_unrelated_claims():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        article_service = ArticleService()
        summary_service = SummaryService()

        article_a = article_service.create_article_from_raw(
            db,
            source_name="S11",
            source_type="api",
            url="https://example.com/s11",
            title="Mars mission update",
            raw_text="The rover captured mineral samples on Mars.",
        )
        article_b = article_service.create_article_from_raw(
            db,
            source_name="S12",
            source_type="api",
            url="https://example.com/s12",
            title="Market update",
            raw_text="Coffee prices dropped in European markets.",
        )

        claim_a = models.Claim(
            article_id=article_a.article_id,
            claim_text="The rover captured mineral samples on Mars.",
            claim_type="observed_fact",
        )
        claim_b = models.Claim(
            article_id=article_b.article_id,
            claim_text="Coffee prices dropped in European markets.",
            claim_type="observed_fact",
        )
        db.add_all([claim_a, claim_b])
        db.flush()

        created = summary_service._build_relations(db, [claim_a, claim_b])

        relations = (
            db.query(models.ClaimRelation)
            .filter(models.ClaimRelation.left_claim_id.in_([claim_a.id, claim_b.id]))
            .filter(models.ClaimRelation.right_claim_id.in_([claim_a.id, claim_b.id]))
            .all()
        )
        assert created == 0
        assert not relations
    finally:
        db.close()
