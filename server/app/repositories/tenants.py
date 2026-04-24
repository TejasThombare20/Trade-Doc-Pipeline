"""Tenant repository."""

from __future__ import annotations

from uuid import UUID

import asyncpg


class TenantRepository:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def list_tenants(self) -> list[asyncpg.Record]:
        return await self._conn.fetch(
            "SELECT id, name, slug, created_at FROM tenants ORDER BY name"
        )

    async def get_tenant_by_slug(self, slug: str) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            "SELECT id, name, slug, created_at FROM tenants WHERE slug = $1",
            slug,
        )

    async def get_tenant_by_id(self, tenant_id: UUID) -> asyncpg.Record | None:
        return await self._conn.fetchrow(
            "SELECT id, name, slug, created_at FROM tenants WHERE id = $1",
            tenant_id,
        )
