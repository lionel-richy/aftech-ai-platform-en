"""Fixtures shared by tests/test_db_*.py — deliberately NOT a conftest.py:
imported explicitly by each file, so we never impose a dependency on
Postgres on the existing tests (FakeRagEngine, etc.), which don't need it
and must keep running without Docker.

pytest.importorskip-style: if Postgres isn't reachable (Docker not
started), every test in these files is SKIPPED, not FAILED — the same
principle as pytest.importorskip("modal") in test_modal_app_loads.py.
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.session import fermer_engine, obtenir_engine, session_administrateur, session_pour_organisation


def postgres_est_joignable() -> bool:
    async def _verifier() -> bool:
        try:
            engine = obtenir_engine()
            async with engine.connect() as connexion:
                await connexion.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 — any error = unavailable
            return False
        finally:
            await fermer_engine()

    return asyncio.run(_verifier())


requiert_postgres = pytest.mark.skipif(
    not postgres_est_joignable(),
    reason="Local PostgreSQL unavailable (see backend/docker-compose.yml: docker compose up -d)",
)


@pytest_asyncio.fixture
async def deux_organisations():
    """Creates 2 real organizations for the duration of the test, then
    deletes them (cascade: also wipes everything inserted inside them)."""
    async with session_administrateur() as session:
        from app.db.repositories import OrganizationRepository

        depot = OrganizationRepository(session)
        suffixe = uuid.uuid4().hex[:8]
        org_a = await depot.creer(f"Org Test A {suffixe}", f"org-test-a-{suffixe}")
        org_b = await depot.creer(f"Org Test B {suffixe}", f"org-test-b-{suffixe}")
        await session.commit()

    yield org_a, org_b

    async with session_administrateur() as session:
        await session.execute(text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": org_a.id, "b": org_b.id})
        await session.commit()


def session_org(organization_id):
    return session_pour_organisation(str(organization_id))
