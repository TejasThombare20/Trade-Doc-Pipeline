"""Document detail and SSE timeline.

Note: multi-file upload now lives at POST /v1/documents (this module). Each
upload creates a Job that bundles the documents; pipelines do not start
until the user calls POST /v1/jobs/{job_id}/start.
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import (
    get_bus_svc,
    get_document_repo,
    get_job_svc,
    get_tenant_context,
)
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.repositories.documents import DocumentRepository
from app.schemas.api import TenantContext
from app.schemas.common import DocumentStatus
from app.schemas.pipeline import DocumentDetail
from app.services.events import SessionBus, encode_sse
from app.services.jobs import JobService, UploadFile as JobUploadFile

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("")
async def upload_documents(
    files: list[UploadFile] = File(...),
    ctx: TenantContext = Depends(get_tenant_context),
    svc: JobService = Depends(get_job_svc),
):
    """Upload one or more files. Creates a single Job that groups them all.

    Pipelines do NOT start here — the client must call POST /v1/jobs/{id}/start
    once the user is done adding files.
    """
    settings = get_settings()
    if not files:
        raise ValidationError("at least one file is required")

    payload: list[JobUploadFile] = []
    for f in files:
        data = await f.read()
        if len(data) > settings.MAX_UPLOAD_BYTES:
            raise ValidationError(
                f"file '{f.filename}' exceeds max size {settings.MAX_UPLOAD_BYTES} bytes"
            )
        payload.append(JobUploadFile(
            filename=f.filename or "document.pdf",
            content_type=f.content_type or "application/pdf",
            data=data,
        ))

    res = await svc.create_job_with_documents(tenant_id=ctx.tenant_id, files=payload)
    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "job_id": str(res["job_id"]),
                "rule_book_id": str(res["rule_book_id"]),
                "status": res["status"],
                "documents": [
                    {**d, "document_id": str(d["document_id"])} for d in res["documents"]
                ],
            },
            "message": "Documents uploaded successfully",
            "statusCode": 200,
        },
    )


@router.get("/{document_id}")
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

    detail = DocumentDetail(
        id=doc["id"],
        tenant_id=doc["tenant_id"],
        job_id=doc["job_id"],
        session_id=doc["session_id"],
        type=doc["type"],
        original_name=doc["original_name"],
        mime_type=doc["mime_type"],
        size_bytes=doc["size_bytes"],
        doc_type=doc["doc_type"],
        status=DocumentStatus(doc["status"]),
        is_active=doc["is_active"],
        created_at=doc["created_at"],
        file_url=f"/v1/files/{doc['id']}" if doc.get("storage_key") else None,
        extraction=_json_loads(extraction_row["tool_output"]) if extraction_row else None,
        validation=_json_loads(validation_row["tool_output"]) if validation_row else None,
        decision=_json_loads(decision_row["tool_output"]) if decision_row else None,
        pipeline_status=session["pipeline_status"] if session else None,
        total_tokens_in=session["total_tokens_in"] if session else 0,
        total_tokens_out=session["total_tokens_out"] if session else 0,
    )
    return JSONResponse(
        status_code=200,
        content={"data": detail.model_dump(mode="json"), "message": "Document fetched successfully", "statusCode": 200},
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
