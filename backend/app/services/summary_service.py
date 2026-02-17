from __future__ import annotations

import json
from dataclasses import dataclass
import re

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app import models
from app.services.cluster_service import ClusterService


@dataclass
class SummaryBuildResult:
    summaries_created: int
    citations_created: int
    relations_created: int


class SummaryService:
    def __init__(self) -> None:
        self.cluster_helper = ClusterService()

    def build_summaries(self, db: Session, cluster_ids: list[str] | None = None) -> SummaryBuildResult:
        query = db.query(models.EventCluster).filter(models.EventCluster.status == "active")
        if cluster_ids:
            query = query.filter(models.EventCluster.id.in_(cluster_ids))
        clusters = query.all()

        summaries_created = 0
        citations_created = 0
        relations_created = 0

        for cluster in clusters:
            claims = db.query(models.Claim).filter(models.Claim.event_cluster_id == cluster.id).all()
            if not claims:
                continue

            relations_created += self._build_relations(db, claims)
            summary = self._build_cluster_summary(db, cluster.id, claims)
            citations_created += self._persist_citations(db, summary.id, summary, claims)
            summaries_created += 1

        db.commit()
        return SummaryBuildResult(
            summaries_created=summaries_created,
            citations_created=citations_created,
            relations_created=relations_created,
        )

    def get_latest_events(self, db: Session, limit: int = 10) -> list[dict]:
        summaries = db.query(models.Summary).order_by(models.Summary.created_at.desc()).limit(limit).all()
        events: list[dict] = []
        for summary in summaries:
            cluster = db.query(models.EventCluster).filter(models.EventCluster.id == summary.event_cluster_id).first()
            claims = db.query(models.Claim).filter(models.Claim.event_cluster_id == summary.event_cluster_id).all()
            source_urls = []
            seen = set()
            for claim in claims:
                article = db.query(models.Article).filter(models.Article.id == claim.article_id).first()
                if article and article.url not in seen:
                    seen.add(article.url)
                    source_urls.append(article.url)

            events.append(
                {
                    "cluster_id": summary.event_cluster_id,
                    "cluster_title": cluster.canonical_title if cluster else "Untitled cluster",
                    "agreed_facts": json.loads(summary.agreed_facts_json),
                    "disputed_claims": json.loads(summary.disputed_claims_json),
                    "unknowns": json.loads(summary.unknowns_json),
                    "confidence_rationale": summary.confidence_rationale,
                    "confidence_score": summary.confidence_score,
                    "source_links": source_urls,
                }
            )
        return events

    def _build_relations(self, db: Session, claims: list[models.Claim]) -> int:
        claim_ids = [claim.id for claim in claims]
        existing = (
            db.query(models.ClaimRelation)
            .filter(or_(models.ClaimRelation.left_claim_id.in_(claim_ids), models.ClaimRelation.right_claim_id.in_(claim_ids)))
            .all()
        )
        for relation in existing:
            db.delete(relation)
        db.flush()

        created = 0
        for idx, left in enumerate(claims):
            left_tokens = self.cluster_helper._tokens(left.claim_text)
            for right in claims[idx + 1 :]:
                right_tokens = self.cluster_helper._tokens(right.claim_text)
                score = self.cluster_helper._jaccard(left_tokens, right_tokens)
                relation_type = None
                # Check contradiction first to avoid classifying strong lexical overlap
                # negation pairs as supports.
                if score >= 0.35 and self._is_negation_mismatch(left.claim_text, right.claim_text):
                    relation_type = "contradicts"
                elif score >= 0.6:
                    relation_type = "supports"
                if relation_type is None:
                    continue
                db.add(
                    models.ClaimRelation(
                        left_claim_id=left.id,
                        right_claim_id=right.id,
                        relation_type=relation_type,
                        score=score,
                    )
                )
                created += 1
        db.flush()
        return created

    @staticmethod
    def _is_negation_mismatch(left: str, right: str) -> bool:
        neg_words = {"not", "no", "never", "without"}
        left_tokens = set(re.findall(r"[a-z0-9]+", left.lower()))
        right_tokens = set(re.findall(r"[a-z0-9]+", right.lower()))
        return (left_tokens & neg_words and not right_tokens & neg_words) or (
            right_tokens & neg_words and not left_tokens & neg_words
        )

    def _build_cluster_summary(self, db: Session, cluster_id: str, claims: list[models.Claim]) -> models.Summary:
        supports = (
            db.query(models.ClaimRelation)
            .filter(models.ClaimRelation.relation_type == "supports")
            .filter(
                and_(
                    models.ClaimRelation.left_claim_id.in_([c.id for c in claims]),
                    models.ClaimRelation.right_claim_id.in_([c.id for c in claims]),
                )
            )
            .all()
        )
        contradicts = (
            db.query(models.ClaimRelation)
            .filter(models.ClaimRelation.relation_type == "contradicts")
            .filter(
                and_(
                    models.ClaimRelation.left_claim_id.in_([c.id for c in claims]),
                    models.ClaimRelation.right_claim_id.in_([c.id for c in claims]),
                )
            )
            .all()
        )

        support_ids = {r.left_claim_id for r in supports} | {r.right_claim_id for r in supports}
        agreed = [c.claim_text for c in claims if c.id in support_ids][:5]
        if not agreed and claims:
            agreed = [claims[0].claim_text]

        disputed = []
        for rel in contradicts[:5]:
            left = next((c for c in claims if c.id == rel.left_claim_id), None)
            if left:
                disputed.append(left.claim_text)

        source_ids = {db.query(models.Article).filter(models.Article.id == c.article_id).first().source_id for c in claims}
        unknowns = []
        confidence = min(1.0, 0.35 + (0.1 * len(support_ids)) + (0.1 * len(source_ids)) - (0.1 * len(disputed)))

        summary = models.Summary(
            event_cluster_id=cluster_id,
            agreed_facts_json=json.dumps(agreed),
            disputed_claims_json=json.dumps(disputed),
            unknowns_json=json.dumps(unknowns),
            confidence_rationale=(
                f"Derived from {len(claims)} claims across {len(source_ids)} sources; "
                f"supports={len(supports)}, contradicts={len(contradicts)}."
            ),
            confidence_score=round(max(confidence, 0.05), 3),
        )
        db.add(summary)
        db.flush()
        return summary

    def _persist_citations(
        self,
        db: Session,
        summary_id: str,
        summary: models.Summary,
        claims: list[models.Claim],
    ) -> int:
        citations_created = 0
        claim_by_text = {claim.claim_text: claim for claim in claims}
        sections = {
            "agreed_facts": json.loads(summary.agreed_facts_json),
            "disputed_claims": json.loads(summary.disputed_claims_json),
            "unknowns": json.loads(summary.unknowns_json),
        }

        for section_name, bullets in sections.items():
            for idx, bullet in enumerate(bullets):
                claim = claim_by_text.get(bullet)
                if claim is None and section_name == "unknowns" and claims:
                    claim = claims[0]
                if claim is None:
                    raise ValueError(f"Citation enforcement failed for section={section_name} bullet={idx}")
                evidence = db.query(models.ClaimEvidence).filter(models.ClaimEvidence.claim_id == claim.id).first()
                if evidence is None:
                    raise ValueError(f"Missing evidence span for claim={claim.id}")
                db.add(
                    models.SummaryCitation(
                        summary_id=summary_id,
                        section=section_name,
                        bullet_index=idx,
                        claim_id=claim.id,
                        evidence_id=evidence.id,
                    )
                )
                citations_created += 1
        db.flush()
        return citations_created
