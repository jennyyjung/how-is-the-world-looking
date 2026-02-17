from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from sqlalchemy.orm import Session

from app import models

TOKEN_SPLIT_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass
class ClusterBuildResult:
    clusters_created: int
    claims_clustered: int
    claims_scanned: int


class ClusterService:
    def build_clusters(
        self,
        db: Session,
        *,
        lookback_hours: int = 72,
        similarity_threshold: float = 0.35,
    ) -> ClusterBuildResult:
        since = datetime.utcnow() - timedelta(hours=lookback_hours)
        candidate_claims = (
            db.query(models.Claim)
            .join(models.Article, models.Claim.article_id == models.Article.id)
            .filter(models.Article.created_at >= since)
            .all()
        )

        clusters_created = 0
        claims_clustered = 0
        scanned = len(candidate_claims)

        active_clusters = db.query(models.EventCluster).filter(models.EventCluster.status == "active").all()
        cluster_token_cache: dict[str, set[str]] = {
            cluster.id: self._tokens(cluster.canonical_title) for cluster in active_clusters
        }

        for claim in candidate_claims:
            tokens = self._tokens(claim.claim_text)
            if not tokens:
                continue

            match = self._best_matching_cluster(tokens, active_clusters, cluster_token_cache, similarity_threshold)
            if match is None:
                cluster = models.EventCluster(canonical_title=self._canonical_title(claim.claim_text), status="active")
                db.add(cluster)
                db.flush()
                active_clusters.append(cluster)
                cluster_token_cache[cluster.id] = tokens
                clusters_created += 1
                match = cluster

            if claim.event_cluster_id != match.id:
                claim.event_cluster_id = match.id
                claims_clustered += 1

        db.commit()
        return ClusterBuildResult(
            clusters_created=clusters_created,
            claims_clustered=claims_clustered,
            claims_scanned=scanned,
        )

    def _best_matching_cluster(
        self,
        claim_tokens: set[str],
        clusters: list[models.EventCluster],
        cluster_token_cache: dict[str, set[str]],
        threshold: float,
    ) -> models.EventCluster | None:
        best_cluster: models.EventCluster | None = None
        best_score = 0.0
        for cluster in clusters:
            score = self._jaccard(claim_tokens, cluster_token_cache.get(cluster.id, set()))
            if score > best_score:
                best_score = score
                best_cluster = cluster

        if best_cluster is None or best_score < threshold:
            return None
        return best_cluster

    @staticmethod
    def _canonical_title(text: str) -> str:
        words = text.strip().split()
        return " ".join(words[:12]) if words else "Untitled cluster"

    @staticmethod
    def _tokens(text: str) -> set[str]:
        normalized = TOKEN_SPLIT_PATTERN.split(text.lower())
        return {token for token in normalized if len(token) > 2}

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        union = len(left | right)
        if union == 0:
            return 0.0
        return intersection / union
