"""Tenant repository. No user schema in Part 1."""

from __future__ import annotations

from uuid import UUID

import asyncpg


async def list_tenants(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT id, name, slug, created_at FROM tenants ORDER BY name"
    )


async def get_tenant_by_slug(conn: asyncpg.Connection, slug: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT id, name, slug, created_at FROM tenants WHERE slug = $1",
        slug,
    )


async def get_tenant_by_id(conn: asyncpg.Connection, tenant_id: UUID) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT id, name, slug, created_at FROM tenants WHERE id = $1",
        tenant_id,
    )
