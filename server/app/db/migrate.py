"""Simple, idempotent SQL migration runner.

Applies every `*.sql` file in backend/migrations/ in filename order,
tracking applied versions in `schema_migrations`. Files must be named
`NNN_description.sql`.
"""

from __future__ import annotations

import re
from pathlib import Path

import asyncpg

from app.core.logging import get_logger

logger = get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
_VERSION_RE = re.compile(r"^(\d{3,})_.+\.sql$")

# Postgres error codes that indicate the migration SQL has already been
# (fully or partially) applied.  Safe to treat as "already done".
_IDEMPOTENT_PG_CODES = {
    "42P07",  # DuplicateTableError
    "42P16",  # InvalidTableDefinition (e.g. constraint already exists)
    "42710",  # DuplicateObjectError (index, type, etc.)
    "23505",  # UniqueViolationError (e.g. seed rows already inserted)
}


async def run_migrations(pool: asyncpg.Pool) -> None:
    if not MIGRATIONS_DIR.exists():
        logger.warning("migrations_dir_missing", extra={"dir": str(MIGRATIONS_DIR)})
        return

    files = sorted(p for p in MIGRATIONS_DIR.iterdir() if _VERSION_RE.match(p.name))
    if not files:
        logger.warning("no_migrations_found", extra={"dir": str(MIGRATIONS_DIR)})
        return

    async with pool.acquire() as conn:
        # Bootstrap schema_migrations if this is a fresh DB.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        applied = {
            r["version"]
            for r in await conn.fetch("SELECT version FROM schema_migrations")
        }

        for path in files:
            version = _VERSION_RE.match(path.name).group(1)  # type: ignore[union-attr]
            if version in applied:
                logger.debug("migration_already_applied", extra={"version": version})
                continue

            sql = path.read_text()
            logger.info("applying_migration", extra={"version": version, "file": path.name})

            try:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1) "
                        "ON CONFLICT (version) DO NOTHING",
                        version,
                    )
                logger.info("migration_applied", extra={"version": version})

            except asyncpg.PostgresError as exc:
                pg_code = getattr(exc, "sqlstate", None)
                if pg_code in _IDEMPOTENT_PG_CODES:
                    # Objects already exist — mark as applied and move on.
                    logger.warning(
                        "migration_already_exists",
                        extra={
                            "version": version,
                            "file": path.name,
                            "pg_code": pg_code,
                            "detail": str(exc),
                        },
                    )
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1) "
                        "ON CONFLICT (version) DO NOTHING",
                        version,
                    )
                else:
                    logger.error(
                        "migration_failed",
                        extra={
                            "version": version,
                            "file": path.name,
                            "pg_code": pg_code,
                            "detail": str(exc),
                        },
                    )
                    raise RuntimeError(
                        f"Migration {path.name} failed (pg_code={pg_code}): {exc}"
                    ) from exc
