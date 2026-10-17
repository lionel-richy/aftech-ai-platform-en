"""Verifies that migration 0001 produced a conforming schema: the 13
business tables, Row-Level Security enabled+forced on the multi-tenant
tables, the restricted application role, and the 4 pre-filled roles."""

import pytest
from sqlalchemy import text

from app.db.models import TENANT_SCOPED_TABLES
from app.db.session import session_administrateur
from db_fixtures import requiert_postgres

pytestmark = requiert_postgres

TABLES_ATTENDUES = {
    "organizations",
    "users",
    "memberships",
    "roles",
    "conversations",
    "messages",
    "documents",
    "document_versions",
    "ingestion_jobs",
    "integrations",
    "audit_events",
    "model_requests",
    "evaluation_results",
}


@pytest.mark.asyncio
async def test_les_13_tables_metier_existent():
    async with session_administrateur() as session:
        resultat = await session.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = {ligne[0] for ligne in resultat.all()}

    assert TABLES_ATTENDUES.issubset(tables)


@pytest.mark.asyncio
async def test_rls_active_et_forcee_sur_chaque_table_multi_locataire():
    async with session_administrateur() as session:
        resultat = await session.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = ANY(:noms)"
            ),
            {"noms": list(TENANT_SCOPED_TABLES)},
        )
        lignes = {ligne[0]: (ligne[1], ligne[2]) for ligne in resultat.all()}

    assert set(lignes) == set(TENANT_SCOPED_TABLES)
    for nom_table, (rls_active, rls_forcee) in lignes.items():
        assert rls_active, f"{nom_table}: RLS should be enabled"
        assert rls_forcee, f"{nom_table}: RLS should be FORCED (even for the owner)"


@pytest.mark.asyncio
async def test_organizations_et_roles_ne_sont_pas_dans_les_tables_multi_locataires():
    # organizations (it's the organization itself) and roles (global
    # catalog) have no organization_id — this is intentional (see models.py).
    assert "organizations" not in TENANT_SCOPED_TABLES
    assert "roles" not in TENANT_SCOPED_TABLES
    assert "users" not in TENANT_SCOPED_TABLES


@pytest.mark.asyncio
async def test_role_applicatif_restreint_existe_sans_bypassrls():
    async with session_administrateur() as session:
        resultat = await session.execute(text("SELECT rolbypassrls FROM pg_roles WHERE rolname = 'aftech_app'"))
        ligne = resultat.first()

    assert ligne is not None, "the aftech_app role should exist (created by migration 0001)"
    assert ligne[0] is False


@pytest.mark.asyncio
async def test_les_4_roles_de_demonstration_sont_pre_remplis():
    async with session_administrateur() as session:
        resultat = await session.execute(text("SELECT key FROM roles ORDER BY key"))
        cles = [ligne[0] for ligne in resultat.all()]

    assert cles == ["ai_manager", "auditor", "org_admin", "user"]
