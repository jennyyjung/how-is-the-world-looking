from __future__ import annotations

import json
from dataclasses import dataclass
import re

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app import models
from app.services.claim_extraction import is_factual_claim_type
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
        if not summaries:
            return []

        cluster_ids = [summary.event_cluster_id for summary in summaries]
        clusters = db.query(models.EventCluster).filter(models.EventCluster.id.in_(cluster_ids)).all()
        cluster_by_id = {cluster.id: cluster for cluster in clusters}

        claim_rows = (
            db.query(models.Claim, models.Article.url)
            .join(models.Article, models.Article.id == models.Claim.article_id)
            .filter(models.Claim.event_cluster_id.in_(cluster_ids))
            .all()
        )
        claims_by_cluster: dict[str, list[tuple[models.Claim, str]]] = {}
        for claim, article_url in claim_rows:
            claims_by_cluster.setdefault(claim.event_cluster_id or "", []).append((claim, article_url))

        events: list[dict] = []
        for summary in summaries:
            cluster = cluster_by_id.get(summary.event_cluster_id)
            claims = claims_by_cluster.get(summary.event_cluster_id, [])
            source_urls = []
            seen = set()
            for _, article_url in claims:
                if article_url not in seen:
                    seen.add(article_url)
                    source_urls.append(article_url)

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
        factual_claims = [claim for claim in claims if is_factual_claim_type(claim.claim_type)]
        if len(factual_claims) < 2:
            return 0

        claim_ids = [claim.id for claim in factual_claims]
        existing = (
            db.query(models.ClaimRelation)
            .filter(or_(models.ClaimRelation.left_claim_id.in_(claim_ids), models.ClaimRelation.right_claim_id.in_(claim_ids)))
            .all()
        )
        for relation in existing:
            db.delete(relation)
        db.flush()

        created = 0
        for idx, left in enumerate(factual_claims):
            left_tokens = self.cluster_helper._tokens(left.claim_text)
            for right in factual_claims[idx + 1 :]:
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
        factual_claims = [claim for claim in claims if is_factual_claim_type(claim.claim_type)]
        if not factual_claims:
            raise ValueError(f"Cluster {cluster_id} has no factual claims available for summary generation")
        claim_context = self._preload_claim_context(db, factual_claims)
        factual_claim_by_id = {claim.id: claim for claim in factual_claims}

        supports = (
            db.query(models.ClaimRelation)
            .filter(models.ClaimRelation.relation_type == "supports")
            .filter(
                and_(
                    models.ClaimRelation.left_claim_id.in_([c.id for c in factual_claims]),
                    models.ClaimRelation.right_claim_id.in_([c.id for c in factual_claims]),
                )
            )
            .all()
        )
        contradicts = (
            db.query(models.ClaimRelation)
            .filter(models.ClaimRelation.relation_type == "contradicts")
            .filter(
                and_(
                    models.ClaimRelation.left_claim_id.in_([c.id for c in factual_claims]),
                    models.ClaimRelation.right_claim_id.in_([c.id for c in factual_claims]),
                )
            )
            .all()
        )

        support_ids = {r.left_claim_id for r in supports} | {r.right_claim_id for r in supports}
        agreed: list[str] = []
        seen_normalized: set[str] = set()
        for claim in factual_claims:
            if claim.id not in support_ids:
                continue
            normalized = self._normalize_claim_text(claim.claim_text)
            if normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            agreed.append(claim.claim_text)
            if len(agreed) == 5:
                break
        if not agreed:
            agreed = [factual_claims[0].claim_text]

        disputed = []
        for rel in contradicts[:5]:
            left = factual_claim_by_id.get(rel.left_claim_id)
            right = factual_claim_by_id.get(rel.right_claim_id)
            if left and right:
                disputed.append(self._format_disputed_pair(left.claim_text, right.claim_text))

        source_ids = set()
        for claim in factual_claims:
            article = db.query(models.Article).filter(models.Article.id == claim.article_id).first()
            if article is not None:
                source_ids.add(article.source_id)

        total_factual = len(factual_claims)
        unique_claim_count = len({self._normalize_claim_text(claim.claim_text) for claim in factual_claims})
        source_ratio = min(1.0, len(source_ids) / max(total_factual, 1))
        unique_claim_ratio = min(1.0, unique_claim_count / max(total_factual, 1))
        support_contradiction_ratio = (len(supports) + 1) / (len(supports) + len(contradicts) + 2)

        normalized_factors = [source_ratio, unique_claim_ratio, support_contradiction_ratio]
        base_confidence = sum(normalized_factors) / len(normalized_factors)

        claim_confidences = [claim.confidence for claim in factual_claims if claim.confidence is not None]
        has_claim_confidence = bool(claim_confidences)
        if has_claim_confidence:
            mean_claim_confidence = sum(claim_confidences) / len(claim_confidences)
            confidence = (0.75 * base_confidence) + (0.25 * mean_claim_confidence)
        else:
            mean_claim_confidence = None
            confidence = base_confidence

        confidence = min(1.0, max(0.0, confidence))
        unknowns = []

        summary = models.Summary(
            event_cluster_id=cluster_id,
            agreed_facts_json=json.dumps(agreed),
            disputed_claims_json=json.dumps(disputed),
            unknowns_json=json.dumps(unknowns),
            confidence_rationale=(
                f"Derived from {total_factual} factual claims across {len(source_ids)} sources; "
                f"source_ratio={source_ratio:.2f}, unique_claim_ratio={unique_claim_ratio:.2f}, "
                f"support_contradiction_ratio={support_contradiction_ratio:.2f}, "
                f"supports={len(supports)}, contradicts={len(contradicts)}"
                + (
                    f", mean_claim_confidence={mean_claim_confidence:.2f}."
                    if has_claim_confidence
                    else "."
                )
            ),
            confidence_score=round(confidence, 3),
        )
        db.add(summary)
        db.flush()
        return summary

    @staticmethod
    def _normalize_claim_text(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

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
                if claim is None and section_name == "disputed_claims":
                    left, right = self._parse_disputed_pair(bullet)
                    claim = claim_by_text.get(left) or claim_by_text.get(right)
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

    @staticmethod
    def _normalize_claim_text(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

    @staticmethod
    def _format_disputed_pair(left_text: str, right_text: str) -> str:
        return f"{left_text} <> {right_text}"

    @staticmethod
    def _parse_disputed_pair(text: str) -> tuple[str, str]:
        if " <> " not in text:
            return text, ""
        left, right = text.split(" <> ", 1)
        return left, right

    def _preload_claim_context(self, db: Session, claims: list[models.Claim]) -> dict[str, dict[str, str]]:
        claim_ids = [claim.id for claim in claims]
        if not claim_ids:
            return {}

        rows = (
            db.query(models.Claim.id, models.Article.source_id, models.Article.url)
            .join(models.Article, models.Article.id == models.Claim.article_id)
            .filter(models.Claim.id.in_(claim_ids))
            .all()
        )
        return {claim_id: {"source_id": source_id, "url": url} for claim_id, source_id, url in rows}
