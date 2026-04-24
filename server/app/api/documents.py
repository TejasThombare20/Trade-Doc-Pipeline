"""Document upload, list, detail, SSE timeline."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import (
    get_bus_svc,
    get_document_repo,
    get_document_svc,
    get_tenant_context,
)
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.repositories.documents import DocumentRepository
from app.schemas.api import DocumentUploadResponse, TenantContext
from app.schemas.common import DocumentStatus
from app.schemas.pipeline import DocumentDetail, DocumentListItem
from app.services.documents import DocumentService
from app.services.events import SessionBus, encode_sse

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload(
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(get_tenant_context),
    svc: DocumentService = Depends(get_document_svc),
):
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise ValidationError(f"file exceeds max size {settings.MAX_UPLOAD_BYTES} bytes")

    res = await svc.upload_and_start_pipeline(
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
async def list_documents(
    ctx: TenantContext = Depends(get_tenant_context),
    repo: DocumentRepository = Depends(get_document_repo),
):
    rows = await repo.list_documents(tenant_id=ctx.tenant_id)
    items: list[DocumentListItem] = []
    for r in rows:
        outcome = None
        if r["type"] == "document":
            dec = await repo.get_latest_decision(
                tenant_id=ctx.tenant_id, document_id=r["id"],
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
async def get_document(
    document_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    repo: DocumentRepository = Depends(get_document_repo),
):
    doc = await repo.get_document(tenant_id=ctx.tenant_id, document_id=document_id)
    if doc is None:
        raise NotFoundError("document not found")

    extraction_row = await repo.get_latest_extraction(
        tenant_id=ctx.tenant_id, document_id=document_id,
    )
    validation_row = await repo.get_latest_validation(
        tenant_id=ctx.tenant_id, document_id=document_id,
    )
    decision_row = await repo.get_latest_decision(
        tenant_id=ctx.tenant_id, document_id=document_id,
    )
    session = None
    if doc["session_id"]:
        session = await repo.get_pipeline_session(
            tenant_id=ctx.tenant_id, session_id=doc["session_id"],
        )

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
        file_url=f"/api/files/{doc['storage_key']}" if doc.get("storage_key") else None,
        extraction=_json_loads(extraction_row["tool_output"]) if extraction_row else None,
        validation=_json_loads(validation_row["tool_output"]) if validation_row else None,
        decision=_json_loads(decision_row["tool_output"]) if decision_row else None,
        pipeline_status=session["pipeline_status"] if session else None,
        total_tokens_in=session["total_tokens_in"] if session else 0,
        total_tokens_out=session["total_tokens_out"] if session else 0,
    )


@router.get("/{document_id}/timeline")
async def timeline_sse(
    document_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    repo: DocumentRepository = Depends(get_document_repo),
    bus: SessionBus = Depends(get_bus_svc),
):
    doc = await repo.get_document(tenant_id=ctx.tenant_id, document_id=document_id)
    if doc is None:
        raise NotFoundError("document not found")

    session_id = doc["session_id"]

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

    runs = await repo.list_runs_for_session(
        tenant_id=ctx.tenant_id, session_id=session_id,
    )
    session = await repo.get_pipeline_session(
        tenant_id=ctx.tenant_id, session_id=session_id,
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

    async def live_stream():
        queue, history = await bus.subscribe(UUID(str(session_id)))
        try:
            snapshot = {
                "event": "snapshot",
                "document_id": str(document_id),
                "document_status": doc["status"],
                "steps": steps,
                "pipeline_status": session["pipeline_status"] if session else "pending",
            }
            yield encode_sse(snapshot)

            for ev in history:
                yield encode_sse(ev)
                if ev.get("event") == "closed":
                    return

            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=30)
                    yield encode_sse(ev)
                    if ev.get("event") == "closed":
                        return
                except asyncio.TimeoutError:
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
