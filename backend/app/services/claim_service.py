from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.services.claim_extraction import ClaimExtractionResult


@dataclass
class ClaimPersistResult:
    claims_created: int
    evidence_created: int


class ClaimService:
    def persist_extracted_claims(
        self,
        db: Session,
        *,
        article: models.Article,
        extraction_result: ClaimExtractionResult,
        extraction_model: str | None = None,
        extraction_version: str | None = None,
    ) -> ClaimPersistResult:
        existing_claims = db.query(models.Claim).filter(models.Claim.article_id == article.id).all()
        existing_claim_ids = [claim.id for claim in existing_claims]

        if existing_claim_ids:
            db.query(models.SummaryCitation).filter(models.SummaryCitation.claim_id.in_(existing_claim_ids)).delete(
                synchronize_session=False
            )
            db.query(models.ClaimRelation).filter(
                or_(
                    models.ClaimRelation.left_claim_id.in_(existing_claim_ids),
                    models.ClaimRelation.right_claim_id.in_(existing_claim_ids),
                )
            ).delete(synchronize_session=False)

        for claim in existing_claims:
            db.delete(claim)
        db.flush()

        created_claims = 0
        created_evidence = 0
        for extracted in extraction_result.claims:
            claim = models.Claim(
                article_id=article.id,
                claim_text=extracted.claim_text,
                claim_type=extracted.claim_type,
                confidence=extracted.confidence,
                extraction_model=extraction_model,
                extraction_version=extraction_version,
            )
            db.add(claim)
            db.flush()
            created_claims += 1

            for ev in extracted.evidence:
                evidence = models.ClaimEvidence(
                    claim_id=claim.id,
                    article_id=article.id,
                    evidence_text=ev.evidence_text,
                    start_char=ev.start_char,
                    end_char=ev.end_char,
                    evidence_type=ev.evidence_type,
                )
                db.add(evidence)
                created_evidence += 1

        db.commit()
        return ClaimPersistResult(claims_created=created_claims, evidence_created=created_evidence)
