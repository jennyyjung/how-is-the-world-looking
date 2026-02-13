# Ingestion Interface (V1)

## Source registry
The system currently ships with three source keys:
- `github_trending_stars`
- `hacker_news`
- `google_news_api`

Defined in `backend/app/config/sources.py`.

## Adapter contract
Each adapter implements:
- `source_key`
- `fetch_items(limit: int) -> list[NormalizedArticle]`

Normalized article fields:
- `source_key`
- `source_name`
- `source_type`
- `url`
- `title`
- `raw_text`
- `published_at`

## Runner behavior
`IngestionRunner.run(...)`:
- Selects adapters by `source_keys` (or all by default).
- Fetches normalized records from each adapter.
- Upserts source records (by source name).
- Cleans raw content into keyword-focused `cleaned_text`.
- Computes SHA-256 `content_hash` and skips duplicates by hash.
- Inserts articles with URL uniqueness protection as a secondary guard.
- Returns per-source ingest/skipped counts.

## API usage
`POST /ingest/run`

Request body:
```json
{
  "source_keys": ["hacker_news", "github_trending_stars"],
  "limit_per_source": 10
}
```

Response body:
```json
{
  "ingested": 12,
  "skipped": 3,
  "sources": {
    "hacker_news": {"fetched": 10, "ingested": 8, "skipped": 2},
    "github_trending_stars": {"fetched": 10, "ingested": 4, "skipped": 1}
  }
}
```
