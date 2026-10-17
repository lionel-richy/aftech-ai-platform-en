# PostgreSQL Database — AFTECH AI Platform

**Status: local development only.** Nothing here is deployed on Modal, no
real production data ever passes through it. This database is the
foundation for future structured persistence, not yet wired into the
application that runs today (see "What's still fictional" below).

## 1. Running locally

```bash
cd backend
docker compose up -d                       # starts Postgres (port 5432)
pip install -r requirements-db.txt         # sqlalchemy, alembic, asyncpg, psycopg
DATABASE_URL_ADMIN="postgresql+psycopg://aftech:aftech-dev-local@localhost:5432/aftech" \
  python -m alembic upgrade head           # applies the migrations
python scripts/seed_postgres_from_existing_data.py   # imports existing demo data
```

Stop: `docker compose down` (keeps the data) or `docker compose down -v` (wipes everything).

## 2. The 13 tables, explained simply

| Table | What it's for |
|---|---|
| `organizations` | A client company. Everything else belongs to an organization. |
| `users` | A person (can belong to several organizations). |
| `roles` | **Global** catalog of the 4 roles already shown in the demo (Administrator, AI Lead, User, Auditor) — not tied to an organization, like a shared dropdown menu. |
| `memberships` | The link "this person, in this organization, has this role". |
| `conversations` | A conversation thread with the AI Assistant. |
| `messages` | Each question/answer of a conversation (never modified afterwards). |
| `documents` | An uploaded PDF: current state (name, status, number of pages...). |
| `document_versions` | The history of EVERY processing attempt for a document (useful for debugging a failure). |
| `ingestion_jobs` | Trace of every index rebuild (today only in Modal logs, lost on restart). |
| `integrations` | State of the connectors (Jira, SharePoint...) — no secret is ever stored here. |
| `audit_events` | The real audit log (replaces the fictional table on the Administration page). |
| `model_requests` | Every question asked to Qwen, stored durably (replaces `metrics.py`, which forgets everything on restart). |
| `evaluation_results` | The detail of each validated or rejected claim (today returned to the client and then never kept). |

**Central rule**: every "business" table (rows above except
`organizations`, `users`, `roles`) has a mandatory `organization_id`
column, and PostgreSQL itself (not just the code) prevents reading or
writing another organization's data — see section 4.

## 3. Relationship diagram

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ MEMBERSHIPS : has
    USERS ||--o{ MEMBERSHIPS : has
    ROLES ||--o{ MEMBERSHIPS : defines

    ORGANIZATIONS ||--o{ CONVERSATIONS : owns
    USERS ||--o{ CONVERSATIONS : starts
    CONVERSATIONS ||--o{ MESSAGES : contains

    ORGANIZATIONS ||--o{ DOCUMENTS : owns
    DOCUMENTS ||--o{ DOCUMENT_VERSIONS : history
    ORGANIZATIONS ||--o{ INGESTION_JOBS : triggers
    DOCUMENTS ||--o{ INGESTION_JOBS : concerns

    ORGANIZATIONS ||--o{ INTEGRATIONS : configures
    ORGANIZATIONS ||--o{ AUDIT_EVENTS : logs
    USERS ||--o{ AUDIT_EVENTS : acts

    ORGANIZATIONS ||--o{ MODEL_REQUESTS : measures
    CONVERSATIONS ||--o{ MODEL_REQUESTS : generates
    MODEL_REQUESTS ||--o{ EVALUATION_RESULTS : details
```

## 4. Multi-tenant isolation (Row-Level Security)

Two distinct PostgreSQL roles, created by the `0001_initial_schema` migration:

- **`aftech`** — owner of the tables, used ONLY by Alembic (migrations)
  and administration scripts. Deliberately bypasses isolation
  (`session_administrateur()`).
- **`aftech_app`** — restricted role, **without** `BYPASSRLS`, used by the
  application day-to-day (`session_pour_organisation(org_id)`). PostgreSQL
  forbids it, at the engine level, from seeing or modifying any row whose
  `organization_id` doesn't match its session context — **even if the
  application code forgets a `WHERE organization_id = ...`**.

This is deliberate and important: if organization filtering relied on
code alone, a single forgotten spot would be enough to leak data between
clients. With Row-Level Security, it's the database itself that refuses.

Real proof (see `backend/tests/test_db_isolation.py`, 5 tests, all run
against a real PostgreSQL):
- one organization cannot see another's conversations, even with no
  filter written in the query;
- impossible to insert a row under another organization's name;
- a "softly deleted" document (soft delete) stays invisible to other organizations.

## 5. Deletion policy

- **Soft delete** (`deleted_at`, restorable): `organizations`, `users`, `memberships`, `documents`, `conversations`.
- **Append-only, never deleted by the app**: `messages`, `audit_events`, `model_requests`, `evaluation_results`, `ingestion_jobs`, `document_versions` — a history is never rewritten.
- **Permanent deletion (GDPR, etc.)**: not yet implemented — would require a periodic purge task, deliberately out of scope here.

## 6. Versioned migrations

Managed by Alembic (`backend/alembic/`). The `0001_initial_schema`
migration is generated from `app/db/models.py` (the schema's source of
truth), then hand-extended for the restricted role and the RLS policies.

```bash
# Create a new migration after modifying app/db/models.py:
python -m alembic revision --autogenerate -m "description of the change"
# Apply it:
python -m alembic upgrade head
# Roll back one step:
python -m alembic downgrade -1
```

## 7. Backup and restore (local development)

```bash
# Backup (pg_dump custom format, compressed):
docker exec aftech-postgres-dev pg_dump -U aftech -Fc aftech > backup.dump

# Restore into an EMPTY database:
docker exec -i aftech-postgres-dev pg_restore -U aftech -d aftech --clean --if-exists < backup.dump
```

For a future real production setup: automated backups + retention
managed by the chosen hosting provider (see the mission report for the
options), never a plain manual `pg_dump`.

## 8. Data access layer

`backend/app/db/repositories.py` — one class per domain
(`DocumentRepository`, `ConversationRepository`, `AuditRepository`,
`ModelRequestRepository`, `RoleRepository`, `OrganizationRepository`),
each receiving a session already opened with the right organization
context. Tested against a real PostgreSQL in
`backend/tests/test_db_repositories.py`.

## 9. What's still fictional after this step

- **The application deployed on Modal keeps working exactly as before**:
  `data/indexes/aftech_documents/manifest.json` remains the source of
  truth for `/ask` and `/documents`, `metrics.py` stays in memory. This
  database is NOT yet wired into `main.py`.
- The frontend's Administration page still shows its hardcoded tables
  (`UTILISATEURS_DEMO`, etc.) — they now have a real equivalent in the
  database (see `scripts/seed_postgres_from_existing_data.py`), but the
  frontend doesn't read them from there yet.
- No real authentication: a single "Demo" user exists across the whole
  app (`Topbar.tsx`), so `user_id`/`organization_id` in the database
  can't yet be filled in by real sessions.
- No billing, no GDPR purge, no actually functional `integrations`
  connector (deliberately out of scope).
