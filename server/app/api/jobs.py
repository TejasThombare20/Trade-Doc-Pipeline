"""Job endpoints — list, detail, start, soft-delete."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_job_svc, get_tenant_context
from app.schemas.api import TenantContext
from app.services.jobs import JobService

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    ctx: TenantContext = Depends(get_tenant_context),
    svc: JobService = Depends(get_job_svc),
):
    rows = await svc.list_jobs(tenant_id=ctx.tenant_id)
    return JSONResponse(
        status_code=200,
        content={
            "data": [_serialize_job(r) for r in rows],
            "message": "Jobs fetched successfully",
            "statusCode": 200,
        },
    )


@router.get("/{job_id}")
async def get_job(
    job_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    svc: JobService = Depends(get_job_svc),
):
    res = await svc.get_job_with_documents(tenant_id=ctx.tenant_id, job_id=job_id)
    return JSONResponse(
        status_code=200,
        content={
            "data": _serialize_job_with_docs(res),
            "message": "Job fetched successfully",
            "statusCode": 200,
        },
    )


@router.post("/{job_id}/start")
async def start_job(
    job_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    svc: JobService = Depends(get_job_svc),
):
    res = await svc.start_job(tenant_id=ctx.tenant_id, job_id=job_id)
    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "job_id": str(res["job_id"]),
                "status": res["status"],
                "document_count": res["document_count"],
            },
            "message": "Job started",
            "statusCode": 200,
        },
    )


@router.delete("/{job_id}")
async def delete_job(
    job_id: UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    svc: JobService = Depends(get_job_svc),
):
    await svc.delete_job(tenant_id=ctx.tenant_id, job_id=job_id)
    return JSONResponse(
        status_code=200,
        content={"data": None, "message": "Job deleted", "statusCode": 200},
    )


def _serialize_job(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "tenant_id": str(r["tenant_id"]),
        "rule_book_id": str(r["rule_book_id"]),
        "status": r["status"],
        "document_count": r["document_count"],
        "is_active": r["is_active"],
        "started_at": r["started_at"].isoformat() if r["started_at"] else None,
        "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
        "created_at": r["created_at"].isoformat(),
        "updated_at": r["updated_at"].isoformat(),
    }


def _serialize_job_with_docs(r: dict) -> dict:
    base = _serialize_job(r)
    base["documents"] = [
        {
            "id": str(d["id"]),
            "original_name": d["original_name"],
            "session_id": str(d["session_id"]) if d["session_id"] else None,
            "doc_type": d["doc_type"],
            "status": d["status"],
            "outcome": d["outcome"],
            "mime_type": d["mime_type"],
            "size_bytes": d["size_bytes"],
            "created_at": d["created_at"].isoformat(),
        }
        for d in r["documents"]
    ]
    return base
