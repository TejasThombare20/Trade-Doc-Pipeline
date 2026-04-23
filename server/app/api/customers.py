"""Customer listing. Operators need this to choose a customer on upload.

Public endpoint — no authentication required. The caller supplies `tenant_id`
as a query parameter so the frontend can fetch the list before (or without)
a session.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from app.db.pool import get_pool
from app.repositories import customers as cust_repo
from app.schemas.api import CustomerSummary

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=list[CustomerSummary])
async def list_customers(tenant_id: UUID = Query(..., description="Tenant to list customers for")):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await cust_repo.list_customers(conn, tenant_id=tenant_id)
    return [
        CustomerSummary(
            id=r["id"], name=r["name"], code=r["code"],
            has_active_rule_book=r["has_active_rule_book"],
        )
        for r in rows
    ]
