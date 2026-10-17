# AFTECH AI Platform

RAG (*Retrieval-Augmented Generation*) document assistant with built-in anti-hallucination verification: every generated claim must be backed by an exact citation, checked word-for-word against the source document, then confirmed by a second, independent model call before being presented as reliable.

## Features

- **AI Assistant** — ask a question, get a **sourced** answer (document, page, exact citation) with a `COMPLETE` / `PARTIAL` / `NOT_FOUND` status reflecting what could actually be verified.
- **Trilingual (fr/en/de)** — the interface and answers adapt to the chosen language; citations, however, always stay in the document's original language (never translated).
- **Library** — browse indexed documents, upload and delete PDFs, with status tracking (`UPLOADED → EXTRACTING → INDEXING → READY/FAILED`) and atomic index rebuilding (never a direct replacement — an invalid version never replaces a working one).
- **Dashboard** — real, measured metrics (latency, status breakdown, comparative T4/L4/A100 GPU benchmark), with no invented numbers.
- **Administration / Integrations** — preview future roles, users and connectors (Jira, SharePoint, GitHub…), clearly marked as demos as long as they aren't wired to real data.

## Architecture

```
frontend/   Next.js 16 (App Router), Tailwind v4, next-intl
backend/    FastAPI + RAG engine (FAISS + BGE-M3 for retrieval, Qwen3-4B-Instruct-2507
            in 4-bit for generation), deployed on Modal (GPU on demand,
            scale-to-zero — no cost while nobody is using the API)
scripts/    Colab tools (GPU benchmark, index building), independent of the backend
docs/       Technical documentation (database schema, etc.)
```

**Anti-hallucination mechanism**: for every generated claim, the model must provide an exact citation taken from the source passage. This citation is first checked **word-for-word** (substring search, no blind trust in the model), then a second — fully independent — call, which only sees the question, the claim and the citation, must confirm that the citation actually proves the claim. A claim is only accepted if both checks pass.

**Cost control**: the GPU (Modal) only starts on the first real question and shuts down automatically after 5 minutes of inactivity. Availability monitoring runs on a separate, strictly CPU-only function, so it never wakes the GPU unnecessarily.

## Running locally

```bash
# Backend (requires a GPU for generation; runs in degraded mode without one)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

PostgreSQL database (foundation for future structured persistence — see [`docs/DATABASE.md`](docs/DATABASE.md)):

```bash
cd backend
docker compose up -d
pip install -r requirements-db.txt
DATABASE_URL_ADMIN="postgresql+psycopg://aftech:aftech-dev-local@localhost:5432/aftech" python -m alembic upgrade head
```

## Tests

```bash
cd backend && pytest        # RAG engine, API, document pipeline, PostgreSQL isolation
cd frontend && npm test     # components, routes, internationalization
```

## Current status

- **Backend**: deployed on Modal, functional (assistant, library, document upload).
- **Frontend**: functional locally, **not yet publicly hosted**.
- **PostgreSQL**: schema and migrations ready, used in local development only — not yet connected to the deployed app.
- **Authentication**: not yet implemented (a single demo profile for now).

## Tech stack

Next.js 16 · TypeScript · Tailwind CSS v4 · FastAPI · Modal · FAISS · BGE-M3 · Qwen3-4B-Instruct · PostgreSQL · SQLAlchemy · Alembic
