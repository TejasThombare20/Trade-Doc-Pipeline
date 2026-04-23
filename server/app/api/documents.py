"""Document upload, list, detail, SSE timeline."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import get_tenant_context
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.db.pool import get_pool
from app.repositories import documents as doc_repo
from app.schemas.api import DocumentUploadResponse, TenantContext
from app.schemas.common import DocumentStatus
from app.schemas.pipeline import (
    DocumentDetail,
    DocumentListItem,
    TimelineStep,
)
from app.services.documents import upload_and_start_pipeline
from app.services.events import encode_sse, get_bus

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload(
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(get_tenant_context),
):
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise ValidationError(f"file exceeds max size {settings.MAX_UPLOAD_BYTES} bytes")

    res = await upload_and_start_pipeline(
        tenant_id=ctx.tenant_id,
        filename=file.filename or "document.pdf",
        content_type=file.content_type or "application/pdf",
        data=data,
    )
    return DocumentUploadResponse(
        document_id=res["document_id"],
        session_id=res["session_id"],
        status=res["status"],
    )


@router.get("", response_model=list[DocumentListItem])
async def list_documents(ctx: TenantContext = Depends(get_tenant_context)):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await doc_repo.list_documents(conn, tenant_id=ctx.tenant_id)
    items: list[DocumentListItem] = []
    for r in rows:
        # Derive outcome from the latest decision's tool_output
        outcome = None
        if r["type"] == "document":
            async with pool.acquire() as conn:
                dec = await doc_repo.get_latest_decision(
                    conn, tenant_id=ctx.tenant_id, document_id=r["id"],
                )
                if dec is not None:
                    to = _json_loads(dec["tool_output"])
                    outcome = to.get("outcome")
        items.append(DocumentListItem(
            id=r["id"],
            original_name=r["original_name"],
            type=r["type"],
            doc_type=r["doc_type"],
            status=DocumentStatus(r["status"]),
            outcome=outcome,
            is_active=r["is_active"],
            created_at=r["created_at"],
        ))
    return items


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: UUID, ctx: TenantContext = Depends(get_tenant_context)):
    pool = get_pool()
    async with pool.acquire() as conn:
        doc = await doc_repo.get_document(
            conn, tenant_id=ctx.tenant_id, document_id=document_id,
        )
        if doc is None:
            raise NotFoundError("document not found")
        extraction_row = await doc_repo.get_latest_extraction(
            conn, tenant_id=ctx.tenant_id, document_id=document_id,
        )
        validation_row = await doc_repo.get_latest_validation(
            conn, tenant_id=ctx.tenant_id, document_id=document_id,
        )
        decision_row = await doc_repo.get_latest_decision(
            conn, tenant_id=ctx.tenant_id, document_id=document_id,
        )
        session = None
        if doc["session_id"]:
            session = await doc_repo.get_pipeline_session(
                conn, tenant_id=ctx.tenant_id, session_id=doc["session_id"],
            )

    extraction = _json_loads(extraction_row["tool_output"]) if extraction_row else None
    validation = _json_loads(validation_row["tool_output"]) if validation_row else None
    decision = _json_loads(decision_row["tool_output"]) if decision_row else None

    return DocumentDetail(
        id=doc["id"],
        tenant_id=doc["tenant_id"],
        session_id=doc["session_id"],
        type=doc["type"],
        original_name=doc["original_name"],
        mime_type=doc["mime_type"],
        size_bytes=doc["size_bytes"],
        doc_type=doc["doc_type"],
        status=DocumentStatus(doc["status"]),
        is_active=doc["is_active"],
        created_at=doc["created_at"],
        extraction=extraction,
        validation=validation,
        decision=decision,
        pipeline_status=session["pipeline_status"] if session else None,
        total_tokens_in=session["total_tokens_in"] if session else 0,
        total_tokens_out=session["total_tokens_out"] if session else 0,
    )


@router.get("/{document_id}/timeline")
async def timeline_sse(document_id: UUID, ctx: TenantContext = Depends(get_tenant_context)):
    """SSE endpoint. Streams pipeline step events in real-time.

    The client connects with EventSource; events arrive as they happen.
    On session completion a 'closed' event is sent and the stream ends.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        doc = await doc_repo.get_document(
            conn, tenant_id=ctx.tenant_id, document_id=document_id,
        )
        if doc is None:
            raise NotFoundError("document not found")

    session_id = doc["session_id"]

    # If no session yet, return current state as a single snapshot
    if session_id is None:
        async def no_session():
            snapshot = {
                "event": "snapshot",
                "document_id": str(document_id),
                "document_status": doc["status"],
                "steps": [],
                "pipeline_status": None,
            }
            yield encode_sse(snapshot)
        return StreamingResponse(no_session(), media_type="text/event-stream")

    # Fetch existing pipeline_runs as initial timeline steps
    async with pool.acquire() as conn:
        runs = await doc_repo.list_runs_for_session(
            conn, tenant_id=ctx.tenant_id, session_id=session_id,
        )
        session = await doc_repo.get_pipeline_session(
            conn, tenant_id=ctx.tenant_id, session_id=session_id,
        )

    steps = [
        {
            "id": str(r["id"]),
            "step_type": r["step_type"],
            "mode": r["mode"],
            "status": r["status"],
            "response": _json_loads(r["response"]) if r["response"] else None,
            "tokens_in": r["total_tokens_in"],
            "tokens_out": r["total_tokens_out"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
        }
        for r in runs
    ]

    # If session is already complete, return snapshot without SSE streaming
    if session and session["pipeline_status"] in ("success", "fail"):
        async def completed_stream():
            snapshot = {
                "event": "snapshot",
                "document_id": str(document_id),
                "document_status": doc["status"],
                "steps": steps,
                "pipeline_status": session["pipeline_status"],
                "total_tokens_in": session["total_tokens_in"],
                "total_tokens_out": session["total_tokens_out"],
            }
            yield encode_sse(snapshot)
            yield encode_sse({"event": "closed"})
        return StreamingResponse(completed_stream(), media_type="text/event-stream")

    # Live stream: send snapshot + subscribe to bus for live events
    bus = get_bus()

    async def live_stream():
        queue, history = await bus.subscribe(UUID(str(session_id)))
        try:
            # Send initial snapshot
            snapshot = {
                "event": "snapshot",
                "document_id": str(document_id),
                "document_status": doc["status"],
                "steps": steps,
                "pipeline_status": session["pipeline_status"] if session else "pending",
            }
            yield encode_sse(snapshot)

            # Replay any events that happened between our DB query and subscription
            for ev in history:
                yield encode_sse(ev)
                if ev.get("event") == "closed":
                    return

            # Stream live events
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=30)
                    yield encode_sse(ev)
                    if ev.get("event") == "closed":
                        return
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield b": keepalive\n\n"
        finally:
            await bus.unsubscribe(UUID(str(session_id)), queue)

    return StreamingResponse(live_stream(), media_type="text/event-stream")


def _json_loads(value):
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return {}
    return json.loads(value)
