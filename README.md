# How Is The World Looking

An MVP news intelligence tool for **tech professionals** who want a neutral, no-fluff view of the latest **technology and GenAI** developments.

## Product goal (current scope)
Given multiple reports about the same tech/genAI event, produce concise factual briefs with source-linked evidence, explicit disagreements, and stated uncertainty.

## MVP focus
- Ingest a small set of tech + GenAI sources.
- Store raw articles and extracted factual claims.
- Clean article content into digestible keywords and dedupe by content hash.
- Cluster claims into event records.
- Produce concise factual summaries with explicit evidence and uncertainty.

## Source registry (v1)
- GitHub Trending/Stars (`github_trending_stars`)
- Hacker News (`hacker_news`)
- Google News API (`google_news_api`)

Environment variables:
- `GITHUB_TOKEN` (optional, increases GitHub API rate limits)
- `GOOGLE_NEWS_API_KEY` (required for Google News adapter)

Content cleaner (MVP):
- Removes basic HTML/URL boilerplate
- Filters common stopwords/news boilerplate terms
- Produces keyword-focused `cleaned_text` and a SHA-256 `content_hash` for dedupe

## What to read first
- `docs/v1-database-schema.md`: v1 relational schema and design notes.
- `docs/first-week-build-plan.md`: implementation sequence for week one and concrete testable MVP gates.
- `docs/tech-genai-mvp-next-steps.md`: missing components and week-two plan to ship a testable MVP.
- `docs/prompts/factual-claim-templates.md`: extraction/summarization prompts and template injections.

## Project layout
- `backend/`: initial FastAPI service and persistence scaffolding.
- `docs/`: product, architecture, prompts, and roadmap docs.

## Quickstart (backend)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Useful endpoints:
- `GET /sources`
- `POST /ingest/run`
- `POST /extract/claims`

Run tests:
```bash
pytest
```


Claim extraction endpoint accepts strict JSON model output and persists claims plus evidence spans for an article.
