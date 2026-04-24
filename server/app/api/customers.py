"""Customer listing."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_customer_repo
from app.repositories.customers import CustomerRepository
from app.schemas.api import CustomerSummary

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=list[CustomerSummary])
async def list_customers(
    tenant_id: UUID = Query(..., description="Tenant to list customers for"),
    repo: CustomerRepository = Depends(get_customer_repo),
):
    rows = await repo.list_customers(tenant_id=tenant_id)
    return [
        CustomerSummary(
            id=r["id"], name=r["name"], code=r["code"],
            has_active_rule_book=r["has_active_rule_book"],
        )
        for r in rows
    ]
