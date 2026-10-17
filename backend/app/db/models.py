"""PostgreSQL schema (SQLAlchemy 2.0, declarative) — LOCAL DEVELOPMENT
ONLY for now (see docs/DATABASE.md). Never imported by app/main.py or
modal_app.py: this layer is optional and not yet wired into the deployed
application.

Guiding principle: EVERY business table carries organization_id, indexed,
with an explicit foreign key constraint to organizations.id — never an
implicit "global" table that would mix data from several organizations
(see tests/test_db_isolation.py for the proof).

Deletion: "soft delete" (deleted_at) for entities we want to be able to
restore (organizations, users, memberships, documents, conversations).
Event/history tables (messages, audit_events, model_requests,
evaluation_results, ingestion_jobs, document_versions) are APPEND-ONLY:
no deleted_at, only a cascading delete if the parent is actually deleted
(see ondelete="CASCADE" on each ForeignKey).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _organization_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# --- Identity / organization ---------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # No organization_id HERE: a user can belong to several organizations
    # (see memberships) — exactly like GitHub/Slack.


class Role(Base):
    """GLOBAL catalog of roles (4 rows, see migration 0001) — not a
    per-organization "business" table: it's a shared reference list, like
    an enum type but editable without a migration. Mirrors exactly the 4
    roles already shown (as a demo) on the Administration page."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)  # "org_admin", "ai_manager", ...
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Membership(Base):
    """Link between organization <-> user <-> role. THIS table is the
    "business" one and carries organization_id — not Role nor User."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = _created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- AI Assistant: conversations ------------------------------------------


class ResponseLanguage(str, enum.Enum):
    fr = "fr"
    en = "en"
    de = "de"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class AnswerStatus(str, enum.Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOT_FOUND = "NOT_FOUND"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """APPEND-ONLY: a question or an answer is never modified after the
    fact (consistent with the anti-hallucination principle already in
    place on the RAG side — we never rewrite history)."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Denormalized: lets us scope/index directly by organization without a
    # join on conversations, and makes multi-tenant isolation verifiable
    # even if a query forgets to go through conversation_id.
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    response_language: Mapped[ResponseLanguage | None] = mapped_column(
        Enum(ResponseLanguage, name="response_language"), nullable=True
    )
    status: Mapped[AnswerStatus | None] = mapped_column(Enum(AnswerStatus, name="answer_status"), nullable=True)
    sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validated_claims: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _created_at()

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)


# --- Documents ---------------------------------------------------------


class DocumentStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    EXTRACTING = "EXTRACTING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"
    DELETING = "DELETING"


class Document(Base):
    """STABLE identity of an uploaded document. The history of each
    processing attempt lives in document_versions — this table only keeps
    the CURRENT state (denormalized for fast reads, e.g. the Library)."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("organization_id", "hash_sha256", name="uq_document_org_hash"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    nom_original: Mapped[str] = mapped_column(String(300), nullable=False)
    nom_stocke: Mapped[str] = mapped_column(String(100), nullable=False)
    taille_octets: Mapped[int] = mapped_column(Integer, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    statut: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status"), nullable=False)
    message_erreur: Mapped[str | None] = mapped_column(Text, nullable=True)
    nb_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nb_passages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.created_at"
    )


class DocumentVersion(Base):
    """APPEND-ONLY history of every processing attempt for a document (one
    row per pass through UPLOADED -> ... -> READY/FAILED). Useful for
    debugging an extraction failure without losing track of previous
    attempts."""

    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    statut: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, name="document_status"), nullable=False)
    message_erreur: Mapped[str | None] = mapped_column(Text, nullable=True)
    nb_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nb_passages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _created_at()

    document: Mapped["Document"] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),)


class IngestionJobType(str, enum.Enum):
    upload_process = "upload_process"
    delete_reindex = "delete_reindex"
    full_reindex = "full_reindex"
    rollback = "rollback"


class IngestionJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class IngestionJob(Base):
    """APPEND-ONLY trace of every index rebuild (see index_builder.py) —
    today only visible in Modal logs, lost on container restart."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    job_type: Mapped[IngestionJobType] = mapped_column(Enum(IngestionJobType, name="ingestion_job_type"), nullable=False)
    statut: Mapped[IngestionJobStatus] = mapped_column(
        Enum(IngestionJobStatus, name="ingestion_job_status"), nullable=False
    )
    message_erreur: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Integrations ---------------------------------------------------------


class IntegrationProvider(str, enum.Enum):
    jira = "jira"
    sharepoint = "sharepoint"
    onedrive = "onedrive"
    google_drive = "google_drive"
    local_folders = "local_folders"
    github = "github"
    gitlab = "gitlab"
    database = "database"


class IntegrationStatus(str, enum.Enum):
    not_connected = "not_connected"
    config_required = "config_required"
    connected = "connected"
    error = "error"


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("organization_id", "provider", name="uq_integration_org_provider"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(IntegrationProvider, name="integration_provider"), nullable=False
    )
    statut: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus, name="integration_status"), nullable=False, default=IntegrationStatus.not_connected
    )
    # NEVER a secret here (API key, token...) — only non-sensitive settings
    # (e.g. a Jira space URL). Real secrets, if they ever arrive, will live
    # in a dedicated secrets manager, not in the database.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --- Audit / metrics / evaluation ---------------------------------------


class AuditEvent(Base):
    """APPEND-ONLY. Eventually replaces JOURNAL_AUDIT_DEMO (fictional data,
    frontend/app/administration/page.tsx)."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)  # "document.uploaded", "question.asked"...
    event_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_audit_events_org_created", "organization_id", "created_at"),)


class ModelRequest(Base):
    """APPEND-ONLY. DURABLE version of what backend/app/metrics.py keeps
    only in process memory (lost on every restart)."""

    __tablename__ = "model_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    response_language: Mapped[ResponseLanguage] = mapped_column(
        Enum(ResponseLanguage, name="response_language"), nullable=False
    )
    status: Mapped[AnswerStatus] = mapped_column(Enum(AnswerStatus, name="answer_status"), nullable=False)
    recherche_secondes: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    generation_secondes: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    total_secondes: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    tokens_entree: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_generes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_model_requests_org_created", "organization_id", "created_at"),)


class EvaluationResult(Base):
    """APPEND-ONLY. Per-claim detail of a validated (or rejected) answer —
    today returned to the client and then never kept server-side."""

    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = _organization_fk()
    model_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_requests.id", ondelete="CASCADE"), nullable=True
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    fichier: Mapped[str | None] = mapped_column(String(300), nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_presente: Mapped[bool] = mapped_column(Boolean, nullable=False)
    preuve_supported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = _created_at()


# "Business" tables carrying organization_id — used by migrations to
# enable Row-Level Security automatically on all of them, without missing
# any.
TENANT_SCOPED_TABLES = (
    "memberships",
    "conversations",
    "messages",
    "documents",
    "document_versions",
    "ingestion_jobs",
    "integrations",
    "audit_events",
    "model_requests",
    "evaluation_results",
)
