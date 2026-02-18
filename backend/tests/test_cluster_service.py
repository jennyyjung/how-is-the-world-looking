import json

from app import models
from app.db import Base, SessionLocal, engine
from app.services.article_service import ArticleService
from app.services.claim_extraction import parse_claim_extraction_json
from app.services.claim_service import ClaimService
from app.services.cluster_service import ClusterService
from app.services.summary_service import SummaryService


def _create_cluster_with_claims(db, source_count: int, claim_texts: list[str], confidence: float | None = None) -> tuple[str, list[models.Claim]]:
    cluster = models.EventCluster(canonical_title="Confidence Test Cluster")
    db.add(cluster)
    db.flush()

    claims: list[models.Claim] = []
    for idx, claim_text in enumerate(claim_texts):
        source = models.Source(name=f"Confidence Source {idx}", source_type="api")
        db.add(source)
        db.flush()
        if idx >= source_count:
            source = db.query(models.Source).filter(models.Source.name == "Confidence Source 0").first()
        article = models.Article(
            source_id=source.id,
            url=f"https://example.com/confidence/{cluster.id}/{idx}",
            title=f"Claim {idx}",
            cleaned_text=claim_text,
        )
        db.add(article)
        db.flush()
        claim = models.Claim(
            article_id=article.id,
            event_cluster_id=cluster.id,
            claim_text=claim_text,
            claim_type="observed_fact",
            confidence=confidence,
        )
        db.add(claim)
        db.flush()
        db.add(
            models.ClaimEvidence(
                claim_id=claim.id,
                article_id=article.id,
                evidence_text=claim_text,
                evidence_type="reported_fact",
            )
        )
        claims.append(claim)

    db.flush()
    return cluster.id, claims


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

        claim_ids = [claim.id for claim in db.query(models.Claim).filter(models.Claim.article_id.in_([a1.article_id, a2.article_id])).all()]
        relations = (
            db.query(models.ClaimRelation)
            .filter(models.ClaimRelation.left_claim_id.in_(claim_ids))
            .filter(models.ClaimRelation.right_claim_id.in_(claim_ids))
            .all()
        )
        assert relations
        assert any(rel.relation_type == "contradicts" for rel in relations)
        assert not any(rel.relation_type == "supports" for rel in relations)

        cluster_id = (
            db.query(models.Claim.event_cluster_id)
            .filter(models.Claim.id == claim_ids[0])
            .scalar()
        )
        latest_summary = (
            db.query(models.Summary)
            .filter(models.Summary.event_cluster_id == cluster_id)
            .order_by(models.Summary.created_at.desc())
            .first()
        )
        assert latest_summary is not None
        disputed = json.loads(latest_summary.disputed_claims_json)
        assert disputed
        assert " <> " in disputed[0]
        assert "increased this quarter" in disputed[0]
        assert "did not increase this quarter" in disputed[0]

        assert "across 2 sources" in latest_summary.confidence_rationale
        assert "contradicts=1" in latest_summary.confidence_rationale

        latest_events = summary_service.get_latest_events(db, limit=20)
        event = next((item for item in latest_events if item["cluster_id"] == cluster_id), None)
        assert event is not None
        assert set(event.keys()) == {
            "cluster_id",
            "cluster_title",
            "agreed_facts",
            "disputed_claims",
            "unknowns",
            "confidence_rationale",
            "confidence_score",
            "source_links",
        }
        assert event["disputed_claims"] == disputed
        assert len(event["source_links"]) == 2
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


def test_confidence_increases_with_more_independent_sources():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        service = SummaryService()
        low_source_cluster, low_source_claims = _create_cluster_with_claims(
            db,
            source_count=1,
            claim_texts=["Power grid restored in district north.", "Power grid restored in district south."],
            confidence=0.8,
        )
        high_source_cluster, high_source_claims = _create_cluster_with_claims(
            db,
            source_count=2,
            claim_texts=["Power grid restored in district north.", "Power grid restored in district south."],
            confidence=0.8,
        )

        low_summary = service._build_cluster_summary(db, low_source_cluster, low_source_claims)
        high_summary = service._build_cluster_summary(db, high_source_cluster, high_source_claims)

        assert high_summary.confidence_score > low_summary.confidence_score
    finally:
        db.close()


def test_confidence_drops_when_contradiction_density_is_high():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        service = SummaryService()
        stable_cluster, stable_claims = _create_cluster_with_claims(
            db,
            source_count=3,
            claim_texts=[
                "Airport resumed operations this morning.",
                "Airport resumed operations this morning per officials.",
                "Airport resumed operations this morning with delays.",
            ],
        )
        contradiction_cluster, contradiction_claims = _create_cluster_with_claims(
            db,
            source_count=3,
            claim_texts=[
                "Airport resumed operations this morning.",
                "Airport did not resume operations this morning.",
                "Airport resumed operations this morning with delays.",
            ],
        )

        service._build_relations(db, stable_claims)
        service._build_relations(db, contradiction_claims)

        stable_summary = service._build_cluster_summary(db, stable_cluster, stable_claims)
        contradiction_summary = service._build_cluster_summary(db, contradiction_cluster, contradiction_claims)

        assert contradiction_summary.confidence_score < stable_summary.confidence_score
    finally:
        db.close()


def test_duplicate_claims_do_not_materially_inflate_confidence():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        service = SummaryService()
        deduped_cluster, deduped_claims = _create_cluster_with_claims(
            db,
            source_count=3,
            claim_texts=[
                "Mayor announced emergency shelter openings.",
                "City confirmed roads are partially reopened.",
                "Emergency services remain on high alert.",
            ],
            confidence=0.9,
        )
        duplicate_cluster, duplicate_claims = _create_cluster_with_claims(
            db,
            source_count=3,
            claim_texts=[
                "Mayor announced emergency shelter openings.",
                "Mayor announced emergency shelter openings.",
                "Mayor announced emergency shelter openings.",
            ],
            confidence=0.9,
        )

        service._build_relations(db, deduped_claims)
        service._build_relations(db, duplicate_claims)

        deduped_summary = service._build_cluster_summary(db, deduped_cluster, deduped_claims)
        duplicate_summary = service._build_cluster_summary(db, duplicate_cluster, duplicate_claims)

        assert duplicate_summary.confidence_score <= deduped_summary.confidence_score + 0.05
    finally:
        db.close()
