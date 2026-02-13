# First-Week Build Plan (MVP)

This week is now scoped to a narrow product target:

> **User goal:** help tech professionals quickly catch up on major tech + latest GenAI developments with neutral, no-fluff factual briefs.

## Day 1: Foundation and schema
- Create repository structure (`backend`, `docs`, tests).
- Implement SQLAlchemy models for Source, Article, Claim, EventCluster.
- Expose health endpoint.
- Add deterministic IDs and timestamp defaults.

## Day 2: Ingestion skeleton
- Add source registry config (3-5 sources):
  - 1 wire-style source
  - 2 major tech publications
  - 1 official vendor/source-of-record feed (company blog/research updates)
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
  - speculation language blacklist in factual bullets.
- Add unit tests for claim parser and validator logic.

## Day 7: Demo slice
- Run ingestion on seed sources.
- Produce 5 event cards for tech/genAI topics.
- Manual QA for factual consistency and confidence calibration.

## What is still missing after Week 1
- Scheduled ingestion jobs (cron/worker) and retry handling.
- A deterministic baseline clusterer and regression tests.
- A concrete source-independence rule to avoid duplicate-wire amplification.
- Event-card API contract for frontend consumption.
- Golden dataset for evaluator checks (citation coverage, factual precision).

## Concrete "testable MVP" definition
The MVP is testable when all of the following are true:
1. Ingests at least 20 fresh tech/genAI articles from configured sources in one run.
2. Extracts claims with evidence for at least 80% of ingested articles.
3. Produces at least 10 event clusters over a rolling 72-hour window.
4. Generates one summary per cluster with 100% sentence-level citation linkage.
5. Passes validator checks for unsupported/speculative factual bullets.

## Deliverables at end of week
- Working API with data persistence.
- End-to-end pipeline for at least one source.
- Prompt templates + output schema validators.
- Clear acceptance criteria for moving into Week 2 hardening.
