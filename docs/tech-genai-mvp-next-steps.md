# Next Steps: Tech + Latest GenAI Concrete MVP

## 1) Product scope (narrow)
Focus only on:
- AI model releases and evaluations.
- Major platform/product announcements from top tech companies.
- AI policy/regulation updates affecting the tech industry.
- Funding/M&A events directly related to AI infrastructure, models, or tooling.

Exclude for MVP:
- Broad world news.
- Opinion columns and long-form thought pieces.
- Non-tech verticals unless directly tied to AI ecosystem impact.

## 2) What is currently missing
From the current scaffold, these pieces are still needed for a concrete user-visible MVP:

### Data ingestion + normalization
- Source registry file with RSS/API adapters.
- Content cleaner implementation (boilerplate removal + dedupe hash).
- Ingestion job runner with idempotent upserts.

### Claim pipeline
- LLM response parser + schema validator that rejects malformed payloads.
- Evidence-span verification against article text.
- Claim type gating so only `observed_fact` and `attributed_statement` feed factual bullets.

### Event pipeline
- Baseline clustering with deterministic fallback.
- Contradiction detection (`supports` / `contradicts`) on claim pairs.
- Cluster confidence calculation from source diversity and support count.

### Summary + trust UX contract
- Structured summary output format:
  - `agreed_facts`
  - `disputed_claims`
  - `unknowns`
  - `confidence_rationale`
- Per-bullet citation IDs and source links.

### Evaluation
- Small golden set (30-50 clusters) for repeatable scoring.
- Metrics dashboard script:
  - citation coverage
  - factual precision (manual review sample)
  - unsupported-claim rate

## 3) Week 2 execution plan to reach a testable MVP

## Day 8-9: ingestion production path
- Implement source registry and one runnable ingestion command.
- Add duplicate URL/content hash protections.
- Save raw and cleaned article text.

**Exit criteria:** one command ingests >=20 articles without crashes.

## Day 10: claim extraction hardening
- Implement extraction service wrapper with strict schema validation.
- Enforce evidence spans and drop unsupported claims.
- Persist claims + evidence records.

**Exit criteria:** >=80% of ingested articles produce valid claims.

## Day 11: clustering + contradiction baseline
- Cluster by time-window + semantic similarity with lexical fallback.
- Generate simple support/contradiction edges for claims in cluster.

**Exit criteria:** >=10 non-trivial event clusters produced.

## Day 12: summary generation + validators
- Generate factual brief per cluster.
- Run post-generation validator and block invalid summaries.
- Expose `GET /events/latest` endpoint returning event cards.

**Exit criteria:** 100% summary bullets include citations.

## Day 13-14: evaluation + demo
- Run quality metrics on golden set and create score snapshot.
- Demo a single "Latest in Tech + GenAI" digest page/API response.

**Exit criteria:** operator can run one command and get refreshed event cards.

## 4) Suggested concrete API surface for MVP
- `POST /ingest/run` - run one ingestion cycle.
- `POST /extract/claims` - extract claims for queued articles.
- `POST /clusters/build` - build/update event clusters.
- `POST /summaries/build` - generate summaries for active clusters.
- `GET /events/latest` - return latest event cards for end-user consumption.

## 5) MVP success criteria (user-centered)
A tech professional should be able to open `GET /events/latest` and, in under 5 minutes:
- see the top 10 current tech/genAI developments,
- read factual bullet summaries without rhetorical framing,
- inspect citations for every bullet,
- identify what is known vs disputed vs unknown.
