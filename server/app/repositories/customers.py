"""Customer repository."""

from __future__ import annotations

from uuid import UUID

import asyncpg


class CustomerRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def list_customers(self, tenant_id: UUID) -> list[asyncpg.Record]:
        return await self._conn.fetch(
            """
            SELECT c.id, c.name, c.code,
                   EXISTS (
                       SELECT 1 FROM documents d
                       WHERE d.tenant_id = c.tenant_id
                         AND d.customer_id = c.id
                         AND d.type = 'rule_book'
                         AND d.is_active = TRUE
                         AND d.status = 'completed'
                   ) AS has_active_rule_book
            FROM customers c
            WHERE c.tenant_id = $1
            ORDER BY c.name
            """,
            tenant_id,
        )

    async def get_customer(self, tenant_id: UUID, customer_id: UUID) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            "SELECT id, tenant_id, name, code FROM customers WHERE tenant_id = $1 AND id = $2",
            tenant_id, customer_id,
        )

    async def get_customer_by_code(self, tenant_id: UUID, code: str) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            "SELECT id, tenant_id, name, code FROM customers WHERE tenant_id = $1 AND code = $2",
            tenant_id, code,
        )
