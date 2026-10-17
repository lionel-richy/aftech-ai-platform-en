"""FastAPI API for the AFTECH AI platform.

Known differences from the official OpenAI API (/v1/chat/completions):
- only the LAST "user" message is used (no server-side multi-turn history:
  conversation memory, if needed, stays on the client side for this
  Demo V1 — see docs/KNOWN_LIMITATIONS.md);
- `usage` (prompt_tokens/completion_tokens/total_tokens) is always 0:
  we haven't instrumented real token counting yet; better to show 0 than
  to make up a number;
- `temperature` is accepted but currently ignored (deterministic generation,
  `do_sample=False`, for reproducibility of validated answers);
- no streaming (no `stream: true`) in this version.
"""

import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import schemas
from .document_manager import DocumentDejaIndexe, DocumentIntrouvable, DocumentManager
from .document_pipeline import FichierInvalide
from .index_builder import ReconstructionDejaEnCours
from .metrics import metrics_store
from .rag_engine import BackendUnavailable, RagEngine
from .security import get_cors_origins, verify_api_key

API_VERSION = "0.1.0"
LIMITE_QUESTION_CARACTERES = 2000
DOCUMENT_STORE_DIR = os.environ.get("DOCUMENT_STORE_DIR", "data/document_store")
TAILLE_MAX_UPLOAD_OCTETS = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024


def _callback_commit_volume_si_modal():
    """None in local/tests (no `modal` required). On Modal, modal_app.py
    defines DOCUMENT_STORE_VOLUME_NAME: we commit the Volume after every
    durable write so it survives a container restart — LAZY import of
    `modal` (never at module level), same as torch/faiss in rag_engine.py."""
    nom_volume = os.environ.get("DOCUMENT_STORE_VOLUME_NAME")
    if not nom_volume:
        return None

    async def _commit() -> None:
        import modal

        # .commit.aio() (not .commit()): Modal's native async equivalent,
        # so this network call never blocks the event loop (see the
        # AsyncUsageWarning observed in production with .commit()).
        await modal.Volume.from_name(nom_volume).commit.aio()

    return _commit


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loaded ONCE per container/process, before serving a single request
    # (so /health never triggers this load).
    engine = RagEngine()
    engine.load()
    app.state.engine = engine
    # Degrades cleanly if the engine couldn't load the embedder (e.g. no
    # index at all locally): DocumentManager only needs engine.embedder,
    # not Qwen — see document_manager.py.
    app.state.document_manager = DocumentManager(
        DOCUMENT_STORE_DIR, engine, TAILLE_MAX_UPLOAD_OCTETS, on_mutation=_callback_commit_volume_si_modal()
    )
    yield


app = FastAPI(title="AFTECH AI Platform API", version=API_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_engine(request: Request) -> RagEngine:
    return request.app.state.engine


def get_document_manager(request: Request) -> DocumentManager:
    return request.app.state.document_manager


def _repondre_ou_erreur(
    engine: RagEngine, question: str, top_k: int, response_language: str = "fr"
) -> tuple[dict, str]:
    """Factors out the error handling shared by /ask and /v1/chat/completions:
    never a traceback returned to the client, always a request_id for
    server-side log diagnostics."""
    request_id = str(uuid.uuid4())
    debut = time.perf_counter()
    try:
        resultat = engine.ask(question, top_k, response_language=response_language)
    except BackendUnavailable as exc:
        metrics_store.record_error()
        raise HTTPException(status_code=503, detail=f"Backend unavailable: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — deliberate: never an opaque 500 with a traceback
        metrics_store.record_error()
        raise HTTPException(
            status_code=500, detail=f"Internal error (request_id={request_id})."
        ) from exc

    metrics_store.record_request(resultat["status"], time.perf_counter() - debut)
    return resultat, request_id


@app.get("/health", response_model=schemas.HealthResponse)
async def health(engine: RagEngine = Depends(get_engine)) -> schemas.HealthResponse:
    info = engine.health()
    return schemas.HealthResponse(version=API_VERSION, **info)


@app.get("/availability")
async def availability() -> dict:
    """Lightweight check: does NOT depend on `engine` (so never a GPU,
    never Qwen/BGE-M3). Only used in local development, where a single
    server answers every route; in production on Modal, it's the SEPARATE
    availability() function (modal_app.py) that answers this same path,
    in a CPU container fully independent from the GPU container."""
    return {"status": "ok", "service": "aftech-ai-platform-availability"}


@app.get(
    "/documents",
    response_model=list[schemas.DocumentItem],
    dependencies=[Depends(verify_api_key)],
)
async def list_documents(gestionnaire: DocumentManager = Depends(get_document_manager)) -> list[dict]:
    return gestionnaire.lister_tout()


@app.post(
    "/documents",
    response_model=schemas.DocumentUploadResponse,
    status_code=201,
    dependencies=[Depends(verify_api_key)],
)
async def upload_document(
    background_tasks: BackgroundTasks,
    fichier: UploadFile,
    gestionnaire: DocumentManager = Depends(get_document_manager),
) -> schemas.DocumentUploadResponse:
    contenu = await fichier.read()
    try:
        enregistrement = await gestionnaire.deposer(contenu, fichier.filename or "document.pdf")
    except FichierInvalide as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentDejaIndexe as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Extraction + indexing as a background task: the HTTP response comes
    # back immediately (UPLOADED status), the client follows progress via
    # GET /documents/{id} (EXTRACTING -> INDEXING -> READY/FAILED).
    background_tasks.add_task(gestionnaire.traiter, enregistrement.id)

    return schemas.DocumentUploadResponse(
        id=enregistrement.id, nom_original=enregistrement.nom_original, statut=enregistrement.statut
    )


@app.get(
    "/documents/{id_document}/status",
    response_model=schemas.DocumentStatusResponse,
    dependencies=[Depends(verify_api_key)],
)
async def document_status(
    id_document: str, gestionnaire: DocumentManager = Depends(get_document_manager)
) -> schemas.DocumentStatusResponse:
    doc = gestionnaire.obtenir_statut(id_document)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return schemas.DocumentStatusResponse(**doc)


@app.delete(
    "/documents/{id_document}",
    status_code=204,
    dependencies=[Depends(verify_api_key)],
)
async def delete_document(
    id_document: str, gestionnaire: DocumentManager = Depends(get_document_manager)
) -> None:
    try:
        await gestionnaire.supprimer(id_document)
    except DocumentIntrouvable as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except ReconstructionDejaEnCours as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/metrics", response_model=schemas.MetricsResponse, dependencies=[Depends(verify_api_key)])
async def get_metrics() -> dict:
    return metrics_store.snapshot()


@app.post("/ask", response_model=schemas.AskResponse, dependencies=[Depends(verify_api_key)])
async def ask(
    payload: schemas.AskRequest, engine: RagEngine = Depends(get_engine)
) -> schemas.AskResponse:
    resultat, request_id = _repondre_ou_erreur(
        engine, payload.question, payload.top_k, response_language=payload.response_language
    )
    return schemas.AskResponse(**resultat, request_id=request_id)


@app.post(
    "/v1/chat/completions",
    response_model=schemas.ChatCompletionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def chat_completions(
    payload: schemas.ChatCompletionRequest, engine: RagEngine = Depends(get_engine)
) -> schemas.ChatCompletionResponse:
    messages_user = [m for m in payload.messages if m.role == "user"]
    if not messages_user:
        raise HTTPException(status_code=400, detail="No 'user' message found.")

    question = messages_user[-1].content
    if len(question) > LIMITE_QUESTION_CARACTERES:
        raise HTTPException(
            status_code=400,
            detail=f"Message too long ({len(question)} characters, max {LIMITE_QUESTION_CARACTERES}).",
        )

    resultat, request_id = _repondre_ou_erreur(engine, question, top_k=8)

    return schemas.ChatCompletionResponse(
        id=f"chatcmpl-{request_id}",
        created=int(time.time()),
        model=payload.model,
        choices=[
            schemas.ChatCompletionChoice(
                index=0,
                message=schemas.ChatMessage(role="assistant", content=resultat["answer"]),
                finish_reason="stop",
            )
        ],
        usage=schemas.ChatCompletionUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )
