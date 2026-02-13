# V1 Database Schema

This schema is designed for factual-news extraction with source provenance and disagreement tracking.

## Core principles
1. Preserve raw source material for traceability.
2. Model claims as first-class objects with evidence spans.
3. Separate event clustering from claim extraction.
4. Track confidence and disagreement explicitly.

## Relational schema (PostgreSQL)

```sql
CREATE TABLE sources (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  homepage_url TEXT,
  country_code TEXT,
  source_type TEXT NOT NULL, -- wire, newspaper, independent, gov, etc.
  reliability_tier SMALLINT DEFAULT 3,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE articles (
  id UUID PRIMARY KEY,
  source_id UUID NOT NULL REFERENCES sources(id),
  url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  author TEXT,
  published_at TIMESTAMPTZ,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  language_code TEXT NOT NULL DEFAULT 'en',
  raw_html TEXT,
  cleaned_text TEXT,
  content_hash TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_articles_source_published ON articles(source_id, published_at DESC);

CREATE TABLE event_clusters (
  id UUID PRIMARY KEY,
  canonical_title TEXT NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status TEXT NOT NULL DEFAULT 'active', -- active, archived
  tags TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE claims (
  id UUID PRIMARY KEY,
  article_id UUID NOT NULL REFERENCES articles(id),
  event_cluster_id UUID REFERENCES event_clusters(id),
  claim_text TEXT NOT NULL,
  subject TEXT,
  predicate TEXT,
  object TEXT,
  occurred_at TIMESTAMPTZ,
  location_text TEXT,
  claim_type TEXT NOT NULL, -- observed_fact, attributed_statement, inference, prediction, opinion
  extraction_model TEXT,
  extraction_version TEXT,
  confidence NUMERIC(4,3),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_claims_article_id ON claims(article_id);
CREATE INDEX idx_claims_event_cluster_id ON claims(event_cluster_id);
CREATE INDEX idx_claims_claim_type ON claims(claim_type);

CREATE TABLE claim_evidence (
  id UUID PRIMARY KEY,
  claim_id UUID NOT NULL REFERENCES claims(id),
  article_id UUID NOT NULL REFERENCES articles(id),
  evidence_text TEXT NOT NULL,
  start_char INT,
  end_char INT,
  evidence_type TEXT NOT NULL DEFAULT 'direct_quote', -- direct_quote, reported_fact, document_reference
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_claim_evidence_claim_id ON claim_evidence(claim_id);

CREATE TABLE claim_relations (
  id UUID PRIMARY KEY,
  left_claim_id UUID NOT NULL REFERENCES claims(id),
  right_claim_id UUID NOT NULL REFERENCES claims(id),
  relation_type TEXT NOT NULL, -- supports, contradicts, duplicates, refines
  relation_confidence NUMERIC(4,3),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(left_claim_id, right_claim_id, relation_type)
);

CREATE TABLE summaries (
  id UUID PRIMARY KEY,
  event_cluster_id UUID NOT NULL REFERENCES event_clusters(id),
  summary_text TEXT NOT NULL,
  uncertainty_text TEXT,
  confidence_score NUMERIC(4,3),
  generated_by TEXT NOT NULL,
  generation_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE summary_citations (
  id UUID PRIMARY KEY,
  summary_id UUID NOT NULL REFERENCES summaries(id),
  claim_id UUID NOT NULL REFERENCES claims(id),
  sentence_index INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_summary_citations_summary_id ON summary_citations(summary_id);
```

## V1 minimal API-aligned entities
- Source
- Article
- Claim
- EventCluster
- Summary

## Deferred for V2
- User personalization
- Source ideological calibration matrix
- Multilingual claim canonicalization
