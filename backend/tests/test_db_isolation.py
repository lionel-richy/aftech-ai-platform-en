"""Proof that one organization can NEVER access another's data —
explicit requirement. Tests go through the restricted application role
"aftech_app" (never the owner role "aftech", which would bypass
Row-Level Security): see app/db/session.py.

If local PostgreSQL isn't started (docker compose up -d), these tests
are SKIPPED, not FAILED (see db_fixtures.requiert_postgres)."""

import uuid

import pytest
from sqlalchemy import select, text

from app.db.models import Conversation, Document, MessageRole
from app.db.repositories import ConversationRepository, DocumentRepository, NouveauMessage
from db_fixtures import deux_organisations, requiert_postgres, session_org  # noqa: F401

pytestmark = requiert_postgres


@pytest.mark.asyncio
async def test_une_organisation_ne_voit_pas_les_conversations_dune_autre(deux_organisations):
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        depot = ConversationRepository(session)
        await depot.creer(org_a.id, title="Conversation privée A")

    async with session_org(org_b.id) as session:
        depot = ConversationRepository(session)
        await depot.creer(org_b.id, title="Conversation privée B")

    async with session_org(org_a.id) as session:
        resultat = await session.execute(select(Conversation))
        conversations = list(resultat.scalars())

    assert len(conversations) == 1
    assert conversations[0].title == "Conversation privée A"


@pytest.mark.asyncio
async def test_meme_sans_filtre_organization_id_dans_la_requete_rien_ne_fuit(deux_organisations):
    """The most important test: NO hand-written WHERE organization_id=...
    — it's PostgreSQL (RLS) doing the filtering, not a coding discipline
    that could be forgotten in a future route."""
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        depot = DocumentRepository(session)
        await depot.creer(org_a.id, "a.pdf", "id-a.pdf", 100, "hash-a")

    async with session_org(org_b.id) as session:
        depot = DocumentRepository(session)
        await depot.creer(org_b.id, "b.pdf", "id-b.pdf", 100, "hash-b")

    async with session_org(org_b.id) as session:
        resultat = await session.execute(select(Document))  # NO .where(organization_id=...)
        documents = list(resultat.scalars())

    assert [d.nom_original for d in documents] == ["b.pdf"]


@pytest.mark.asyncio
async def test_impossible_dinserer_une_ligne_pour_une_autre_organisation(deux_organisations):
    """The WITH CHECK policy must also block a malicious/buggy WRITE
    attempting to insert a row under an organization other than the one
    in the current session context."""
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        with pytest.raises(Exception, match="row-level security|new row violates"):
            await session.execute(
                text(
                    "INSERT INTO conversations (id, organization_id, title) "
                    "VALUES (:id, :org_id, 'malicious injection')"
                ),
                {"id": uuid.uuid4(), "org_id": org_b.id},
            )
            await session.flush()


@pytest.mark.asyncio
async def test_les_messages_dune_conversation_restent_prives_a_lorganisation(deux_organisations):
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        depot = ConversationRepository(session)
        conversation_a = await depot.creer(org_a.id, title="Support A")
        await depot.ajouter_message(
            conversation_a, NouveauMessage(role=MessageRole.user, content="Question confidentielle de A")
        )

    async with session_org(org_b.id) as session:
        from app.db.models import Message

        resultat = await session.execute(select(Message))
        messages_visibles_par_b = list(resultat.scalars())

    assert messages_visibles_par_b == []


@pytest.mark.asyncio
async def test_suppression_douce_dun_document_najoute_pas_de_fuite(deux_organisations):
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        depot = DocumentRepository(session)
        document = await depot.creer(org_a.id, "secret.pdf", "id-secret.pdf", 10, "hash-secret")
        await depot.marquer_supprime(document)

    async with session_org(org_b.id) as session:
        resultat = await session.execute(select(Document))
        assert list(resultat.scalars()) == []
