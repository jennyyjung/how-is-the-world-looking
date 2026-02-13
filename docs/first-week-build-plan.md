# First-Week Build Plan (MVP)

## Day 1: Foundation and schema
- Create repository structure (`backend`, `docs`, tests).
- Implement SQLAlchemy models for Source, Article, Claim, EventCluster.
- Expose health endpoint.
- Add deterministic IDs and timestamp defaults.

## Day 2: Ingestion skeleton
- Add source registry config (3-5 sources).
- Build ingestion interface (`fetch -> normalize -> store`).
- Persist articles with unique URL protection.

## Day 3: Cleaning and claim extraction
- Add article cleaning stage placeholder.
- Add prompt-driven claim extraction service with strict JSON schema output.
- Persist extracted claims and evidence spans.

## Day 4: Event clustering (baseline)
- Implement simple event clustering:
  - title/text embedding similarity or lexical fallback.
  - time-window constraints.
- Attach claims to cluster IDs.

## Day 5: Factual summary generation
- Build cluster-level summary endpoint.
- Generate:
  - agreed facts
  - disputed claims
  - unknowns
- Require citation linkage per summary sentence.

## Day 6: Quality gates
- Add validators:
  - no unsupported summary sentence.
  - no opinion/prediction in factual bullets.
- Add unit tests for claim parser and validator logic.

## Day 7: Demo slice
- Run ingestion on seed sources.
- Produce 5 event cards.
- Manual QA for factual consistency and confidence calibration.

## Deliverables at end of week
- Working API with data persistence.
- End-to-end pipeline for at least one source.
- Prompt templates + output schema validators.
