"""Data access layer — LOCAL DEVELOPMENT ONLY (see docs/DATABASE.md). Each
repository takes an AsyncSession already opened with the right
organization context (see
app/db/session.py:session_pour_organisation) — organization_id is never
passed in as a parameter here: Row-Level Security enforces it, not
application code that could forget to call it (see
tests/test_db_isolation.py).

Exception: OrganizationRepository, which is NOT scoped by organization by
nature (creating/listing organizations is an administration operation —
uses session_administrateur, never session_pour_organisation).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AnswerStatus,
    AuditEvent,
    Conversation,
    Document,
    DocumentStatus,
    DocumentVersion,
    Message,
    MessageRole,
    ModelRequest,
    Organization,
    ResponseLanguage,
    Role,
)


class OrganizationRepository:
    """Administration only — use session_administrateur()."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def creer(self, name: str, slug: str) -> Organization:
        organisation = Organization(name=name, slug=slug)
        self.session.add(organisation)
        await self.session.flush()
        return organisation

    async def obtenir_par_slug(self, slug: str) -> Organization | None:
        resultat = await self.session.execute(select(Organization).where(Organization.slug == slug))
        return resultat.scalar_one_or_none()

    async def lister(self) -> list[Organization]:
        resultat = await self.session.execute(select(Organization).where(Organization.deleted_at.is_(None)))
        return list(resultat.scalars())


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def creer(
        self,
        organization_id: uuid.UUID,
        nom_original: str,
        nom_stocke: str,
        taille_octets: int,
        hash_sha256: str,
    ) -> Document:
        document = Document(
            organization_id=organization_id,
            nom_original=nom_original,
            nom_stocke=nom_stocke,
            taille_octets=taille_octets,
            hash_sha256=hash_sha256,
            statut=DocumentStatus.UPLOADED,
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def trouver_par_hash(self, hash_sha256: str) -> Document | None:
        resultat = await self.session.execute(
            select(Document).where(Document.hash_sha256 == hash_sha256, Document.deleted_at.is_(None))
        )
        return resultat.scalar_one_or_none()

    async def obtenir(self, document_id: uuid.UUID) -> Document | None:
        resultat = await self.session.execute(select(Document).where(Document.id == document_id))
        return resultat.scalar_one_or_none()

    async def lister(self) -> list[Document]:
        resultat = await self.session.execute(select(Document).where(Document.deleted_at.is_(None)))
        return list(resultat.scalars())

    async def ajouter_version(
        self,
        document: Document,
        statut: DocumentStatus,
        nb_pages: int = 0,
        nb_passages: int = 0,
        message_erreur: str | None = None,
    ) -> DocumentVersion:
        # Counted via an explicit query, never document.versions (a lazy
        # relationship that would require synchronous access incompatible
        # with AsyncSession — see sqlalchemy.exc.MissingGreenlet).
        resultat_compte = await self.session.execute(
            select(func.count()).select_from(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        numero = resultat_compte.scalar_one() + 1
        version = DocumentVersion(
            organization_id=document.organization_id,
            document_id=document.id,
            version_number=numero,
            statut=statut,
            nb_pages=nb_pages,
            nb_passages=nb_passages,
            message_erreur=message_erreur,
        )
        document.statut = statut
        document.nb_pages = nb_pages or document.nb_pages
        document.nb_passages = nb_passages or document.nb_passages
        document.message_erreur = message_erreur
        self.session.add(version)
        await self.session.flush()
        return version

    async def marquer_supprime(self, document: Document) -> None:
        from datetime import datetime, timezone

        document.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()


@dataclass
class NouveauMessage:
    role: MessageRole
    content: str
    response_language: ResponseLanguage | None = None
    status: AnswerStatus | None = None
    sources: list | None = None
    validated_claims: list | None = None
    timings: dict | None = None
    request_id: str | None = None


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def creer(self, organization_id: uuid.UUID, user_id: uuid.UUID | None = None, title: str | None = None) -> Conversation:
        conversation = Conversation(organization_id=organization_id, user_id=user_id, title=title)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def ajouter_message(self, conversation: Conversation, message: NouveauMessage) -> Message:
        ligne = Message(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            role=message.role,
            content=message.content,
            response_language=message.response_language,
            status=message.status,
            sources=message.sources,
            validated_claims=message.validated_claims,
            timings=message.timings,
            request_id=message.request_id,
        )
        self.session.add(ligne)
        await self.session.flush()
        return ligne

    async def lister(self) -> list[Conversation]:
        resultat = await self.session.execute(select(Conversation).where(Conversation.deleted_at.is_(None)))
        return list(resultat.scalars())

    async def messages_de(self, conversation_id: uuid.UUID) -> list[Message]:
        resultat = await self.session.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
        )
        return list(resultat.scalars())


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enregistrer(
        self, organization_id: uuid.UUID, event_type: str, actor_user_id: uuid.UUID | None = None, metadata: dict | None = None
    ) -> AuditEvent:
        evenement = AuditEvent(
            organization_id=organization_id, event_type=event_type, actor_user_id=actor_user_id, event_metadata=metadata
        )
        self.session.add(evenement)
        await self.session.flush()
        return evenement

    async def lister_recents(self, limite: int = 50) -> list[AuditEvent]:
        resultat = await self.session.execute(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limite)
        )
        return list(resultat.scalars())


class ModelRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enregistrer(
        self,
        organization_id: uuid.UUID,
        request_id: str,
        response_language: ResponseLanguage,
        status: AnswerStatus,
        recherche_secondes: float,
        generation_secondes: float,
        total_secondes: float,
        conversation_id: uuid.UUID | None = None,
        tokens_entree: int | None = None,
        tokens_generes: int | None = None,
    ) -> ModelRequest:
        ligne = ModelRequest(
            organization_id=organization_id,
            conversation_id=conversation_id,
            request_id=request_id,
            response_language=response_language,
            status=status,
            recherche_secondes=recherche_secondes,
            generation_secondes=generation_secondes,
            total_secondes=total_secondes,
            tokens_entree=tokens_entree,
            tokens_generes=tokens_generes,
        )
        self.session.add(ligne)
        await self.session.flush()
        return ligne

    async def snapshot(self) -> dict:
        """Durable equivalent of metrics.MetricsStore.snapshot() — but reads
        real rows, never lost when the container restarts."""
        from sqlalchemy import func as sa_func

        resultat = await self.session.execute(
            select(ModelRequest.status, sa_func.count()).group_by(ModelRequest.status)
        )
        compte_par_statut = {statut.value: n for statut, n in resultat.all()}
        resultat_total = await self.session.execute(select(sa_func.count()).select_from(ModelRequest))
        return {
            "requests_total": resultat_total.scalar_one(),
            "status_complete": compte_par_statut.get("COMPLETE", 0),
            "status_partial": compte_par_statut.get("PARTIAL", 0),
            "status_not_found": compte_par_statut.get("NOT_FOUND", 0),
        }


class RoleRepository:
    """Global catalog (not scoped by organization — see models.py)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def obtenir_par_cle(self, key: str) -> Role | None:
        resultat = await self.session.execute(select(Role).where(Role.key == key))
        return resultat.scalar_one_or_none()

    async def lister(self) -> list[Role]:
        resultat = await self.session.execute(select(Role))
        return list(resultat.scalars())
