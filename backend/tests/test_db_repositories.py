"""Tests the data access layer (app/db/repositories.py) against a REAL
local PostgreSQL — no test double/mock: the real constraints (foreign
keys, uniqueness, RLS) are exactly what we want to verify."""

import pytest

from app.db.models import AnswerStatus, DocumentStatus, MessageRole, ResponseLanguage
from app.db.repositories import (
    AuditRepository,
    ConversationRepository,
    DocumentRepository,
    ModelRequestRepository,
    NouveauMessage,
    RoleRepository,
)
from db_fixtures import deux_organisations, requiert_postgres, session_org

pytestmark = requiert_postgres


@pytest.mark.asyncio
async def test_creer_un_document_puis_le_faire_progresser_jusqua_ready(deux_organisations):
    org_a, _ = deux_organisations

    async with session_org(org_a.id) as session:
        depot = DocumentRepository(session)
        document = await depot.creer(org_a.id, "rapport.pdf", "abc123.pdf", 1024, "hash-unique-1")
        assert document.statut == DocumentStatus.UPLOADED

        await depot.ajouter_version(document, DocumentStatus.EXTRACTING)
        await depot.ajouter_version(document, DocumentStatus.INDEXING)
        version_finale = await depot.ajouter_version(document, DocumentStatus.READY, nb_pages=10, nb_passages=25)

        assert document.statut == DocumentStatus.READY
        assert document.nb_pages == 10
        assert document.nb_passages == 25
        assert version_finale.version_number == 3  # full history: 3 attempts


@pytest.mark.asyncio
async def test_doublon_sha256_rejete_par_une_contrainte_reelle_de_la_base(deux_organisations):
    org_a, _ = deux_organisations

    async with session_org(org_a.id) as session:
        depot = DocumentRepository(session)
        await depot.creer(org_a.id, "a.pdf", "a.pdf", 10, "hash-doublon")

        with pytest.raises(Exception, match="unique|duplicate"):
            await depot.creer(org_a.id, "copie.pdf", "copie.pdf", 10, "hash-doublon")


@pytest.mark.asyncio
async def test_meme_hash_accepte_dans_une_AUTRE_organisation(deux_organisations):
    # The uniqueness constraint is (organization_id, hash_sha256) — not
    # global: two organizations can legitimately upload the same public
    # PDF without conflicting.
    org_a, org_b = deux_organisations

    async with session_org(org_a.id) as session:
        await DocumentRepository(session).creer(org_a.id, "a.pdf", "a.pdf", 10, "hash-partage")

    async with session_org(org_b.id) as session:
        document_b = await DocumentRepository(session).creer(org_b.id, "a.pdf", "a-bis.pdf", 10, "hash-partage")
        assert document_b.hash_sha256 == "hash-partage"


@pytest.mark.asyncio
async def test_conversation_avec_plusieurs_messages(deux_organisations):
    org_a, _ = deux_organisations

    async with session_org(org_a.id) as session:
        depot = ConversationRepository(session)
        conversation = await depot.creer(org_a.id, title="Question sur Azure")
        await depot.ajouter_message(conversation, NouveauMessage(role=MessageRole.user, content="Quel document parle d'Azure ?"))
        await depot.ajouter_message(
            conversation,
            NouveauMessage(
                role=MessageRole.assistant,
                content="Azure propose du stockage. [source : doc.pdf, page 1]",
                response_language=ResponseLanguage.fr,
                status=AnswerStatus.COMPLETE,
            ),
        )

        messages = await depot.messages_de(conversation.id)

    assert len(messages) == 2
    assert messages[0].role == MessageRole.user
    assert messages[1].status == AnswerStatus.COMPLETE


@pytest.mark.asyncio
async def test_audit_event_enregistre_et_relu(deux_organisations):
    org_a, _ = deux_organisations

    async with session_org(org_a.id) as session:
        depot = AuditRepository(session)
        await depot.enregistrer(org_a.id, "document.uploaded", metadata={"nom": "rapport.pdf"})

        evenements = await depot.lister_recents()

    assert any(e.event_type == "document.uploaded" for e in evenements)


@pytest.mark.asyncio
async def test_model_request_et_snapshot_des_metriques(deux_organisations):
    org_a, _ = deux_organisations

    async with session_org(org_a.id) as session:
        depot = ModelRequestRepository(session)
        await depot.enregistrer(
            org_a.id, "req-1", ResponseLanguage.fr, AnswerStatus.COMPLETE, 0.5, 20.0, 20.5
        )
        await depot.enregistrer(
            org_a.id, "req-2", ResponseLanguage.fr, AnswerStatus.NOT_FOUND, 0.3, 1.0, 1.3
        )

        snapshot = await depot.snapshot()

    assert snapshot["requests_total"] == 2
    assert snapshot["status_complete"] == 1
    assert snapshot["status_not_found"] == 1


@pytest.mark.asyncio
async def test_catalogue_des_roles_est_accessible_en_lecture(deux_organisations):
    org_a, _ = deux_organisations

    async with session_org(org_a.id) as session:
        roles = await RoleRepository(session).lister()

    assert {r.key for r in roles} == {"org_admin", "ai_manager", "user", "auditor"}
