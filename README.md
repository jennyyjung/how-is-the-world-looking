# How Is The World Looking

An MVP for a personal news aggregator focused on extracting factual claims, reducing framing, and presenting evidence-backed event summaries.

## MVP focus
- Ingest a small set of sources.
- Store raw articles and extracted claims.
- Cluster claims into event records.
- Produce concise factual summaries with explicit evidence and uncertainty.

## Project layout
- `docs/v1-database-schema.md`: v1 relational schema and design notes.
- `docs/first-week-build-plan.md`: implementation sequence for week one.
- `docs/prompts/factual-claim-templates.md`: extraction/summarization prompts and template injections.
- `backend/`: initial FastAPI service and persistence scaffolding.

## Quickstart (backend)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Run tests:
```bash
pytest
```
