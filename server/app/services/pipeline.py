"""Sequential pipeline: parse -> extract -> validate -> decide.

Every step writes a pipeline_runs row (pending -> success/fail). The
pipeline_sessions row holds the rollup. Retries create new pipeline_runs
rows for the same session.

Each step also publishes an event on the session bus so SSE subscribers
see live progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.agents.extractor import run_extractor
from app.agents.router import run_router
from app.agents.rule_book_extractor import extract_rule_book
from app.agents.validator import run_validator
from app.core.errors import RuleBookMissingError
from app.core.logging import get_logger, set_correlation_id
from app.db.pool import get_pool
from app.repositories import documents as doc_repo
from app.schemas.rules import RuleSpec
from app.schemas.common import Severity
from app.services.events import get_bus
from app.services.preprocessing import preprocess
from app.storage import get_storage

logger = get_logger(__name__)


@dataclass
class StepContext:
    tenant_id: UUID
    document_id: UUID
    session_id: UUID
    type: str  # "document" or "rule_book"


async def init_pipeline() -> None:
    return None


async def shutdown_pipeline() -> None:
    return None


# ------------------------------ helpers ------------------------------

async def _start_step(ctx: StepContext, step_type: str, mode: str) -> UUID:
    pool = get_pool()
    async with pool.acquire() as conn:
        run_id = await doc_repo.start_pipeline_run(
            conn,
            tenant_id=ctx.tenant_id,
            session_id=ctx.session_id,
            document_id=ctx.document_id,
            type=ctx.type,  # type: ignore[arg-type]
            step_type=step_type,  # type: ignore[arg-type]
            mode=mode,  # type: ignore[arg-type]
        )
    await get_bus().publish(ctx.session_id, {
        "event": "step_started",
        "step_type": step_type,
        "mode": mode,
        "run_id": str(run_id),
    })
    return run_id


async def _finish_step(
    ctx: StepContext,
    run_id: UUID,
    status: str,
    response: dict | list | None,
    tokens_in: int | None,
    tokens_out: int | None,
    step_type: str,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await doc_repo.finish_pipeline_run(
            conn,
            tenant_id=ctx.tenant_id,
            run_id=run_id,
            status=status,  # type: ignore[arg-type]
            response=response,
            total_tokens_in=tokens_in,
            total_tokens_out=tokens_out,
        )
    await get_bus().publish(ctx.session_id, {
        "event": "step_completed",
        "step_type": step_type,
        "run_id": str(run_id),
        "status": status,
        "response": response,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    })


async def _complete_session(
    ctx: StepContext, status: str, tokens_in: int, tokens_out: int, error: str | None
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await doc_repo.complete_pipeline_session(
            conn,
            tenant_id=ctx.tenant_id,
            session_id=ctx.session_id,
            status=status,  # type: ignore[arg-type]
            total_tokens_in=tokens_in,
            total_tokens_out=tokens_out,
            error_message=error,
        )
    await get_bus().publish(ctx.session_id, {
        "event": "session_completed",
        "status": status,
        "total_tokens_in": tokens_in,
        "total_tokens_out": tokens_out,
        "error": error,
    })
    await get_bus().close(ctx.session_id)


# ------------------------------ entrypoints ------------------------------

async def run_document_pipeline(
    *,
    tenant_id: UUID,
    document_id: UUID,
    session_id: UUID,
    storage_key: str,
    mime_type: str,
    original_name: str,
) -> None:
    """Parse -> extract -> validate -> decide, logging each step."""
    set_correlation_id(f"sess-{session_id.hex[:12]}")
    ctx = StepContext(
        tenant_id=tenant_id, document_id=document_id,
        session_id=session_id, type="document",
    )
    bus = get_bus()
    await bus.publish(session_id, {"event": "session_started", "type": "document"})

    tokens_in = 0
    tokens_out = 0
    pool = get_pool()

    # Preflight: tenant must have an active rule book.
    async with pool.acquire() as conn:
        active_rb = await doc_repo.get_active_rule_book(
            conn, tenant_id=tenant_id,
        )
    if active_rb is None:
        await _complete_session(ctx, "fail", 0, 0, "no_active_rule_book")
        raise RuleBookMissingError("Tenant has no active rule book.")

    # -------- step 1: parsing (manual) --------
    run_id = await _start_step(ctx, "parsing", "manual")
    try:
        storage = get_storage()
        data = await storage.get(storage_key)
        pre = await preprocess(data, mime_type, original_name)
        parsing_response = {
            "source_kind": pre.source_kind,
            "page_count": pre.page_count,
            "text_len": len(pre.text),
            "image_count": len(pre.images_b64),
            "notes": pre.notes,
            "parsed_text": _truncate_parsed_text(pre.text),
        }
    except Exception as exc:
        logger.exception("parsing_failed")
        await _finish_step(ctx, run_id, "fail", {"error": str(exc)}, None, None, "parsing")
        async with pool.acquire() as conn:
            await doc_repo.update_document_status(
                conn, tenant_id=tenant_id, document_id=document_id, status="failed",
            )
        await _complete_session(ctx, "fail", tokens_in, tokens_out, f"parsing: {exc}")
        return
    await _finish_step(ctx, run_id, "success", parsing_response, None, None, "parsing")

    async with pool.acquire() as conn:
        await doc_repo.update_document_status(
            conn, tenant_id=tenant_id, document_id=document_id, status="extracting",
        )

    rules = _rules_from_extracted(active_rb["extracted_rules"])

    # -------- step 2: extraction (llm) --------
    run_id = await _start_step(ctx, "extraction", "llm")
    try:
        ext_res = await run_extractor(pre, rules=rules)
    except Exception as exc:
        logger.exception("extraction_failed")
        await _finish_step(ctx, run_id, "fail", {"error": str(exc)}, None, None, "extraction")
        async with pool.acquire() as conn:
            await doc_repo.update_document_status(
                conn, tenant_id=tenant_id, document_id=document_id, status="failed",
            )
        await _complete_session(ctx, "fail", tokens_in, tokens_out, f"extraction: {exc}")
        return

    tokens_in += ext_res.usage.tokens_in
    tokens_out += ext_res.usage.tokens_out
    await _finish_step(
        ctx, run_id, "success",
        {"tool_content": ext_res.tool_content, "tool_output": ext_res.tool_output},
        ext_res.usage.tokens_in, ext_res.usage.tokens_out, "extraction",
    )
    async with pool.acquire() as conn:
        await doc_repo.insert_extraction(
            conn,
            tenant_id=tenant_id, document_id=document_id,
            session_id=session_id, pipeline_run_id=run_id,
            tool_content=ext_res.tool_content, tool_output=ext_res.tool_output,
        )
        await doc_repo.update_document_status(
            conn, tenant_id=tenant_id, document_id=document_id,
            status="validating", doc_type=ext_res.output.doc_type.value,
        )

    # -------- step 3: validation (llm) --------
    run_id = await _start_step(ctx, "validation", "llm")
    try:
        val_res = await run_validator(extraction=ext_res.output, rules=rules)
    except Exception as exc:
        logger.exception("validation_failed")
        await _finish_step(ctx, run_id, "fail", {"error": str(exc)}, None, None, "validation")
        async with pool.acquire() as conn:
            await doc_repo.update_document_status(
                conn, tenant_id=tenant_id, document_id=document_id, status="failed",
            )
        await _complete_session(ctx, "fail", tokens_in, tokens_out, f"validation: {exc}")
        return

    tokens_in += val_res.usage.tokens_in
    tokens_out += val_res.usage.tokens_out
    await _finish_step(
        ctx, run_id, "success",
        {"tool_content": val_res.tool_content, "tool_output": val_res.tool_output},
        val_res.usage.tokens_in, val_res.usage.tokens_out, "validation",
    )
    async with pool.acquire() as conn:
        await doc_repo.insert_validation(
            conn,
            tenant_id=tenant_id, document_id=document_id,
            session_id=session_id, pipeline_run_id=run_id,
            tool_content=val_res.tool_content, tool_output=val_res.tool_output,
        )
        await doc_repo.update_document_status(
            conn, tenant_id=tenant_id, document_id=document_id, status="deciding",
        )

    # -------- step 4: decision (llm) --------
    run_id = await _start_step(ctx, "decision", "llm")
    try:
        dec_res = await run_router(val_res.output)
    except Exception as exc:
        logger.exception("decision_failed")
        await _finish_step(ctx, run_id, "fail", {"error": str(exc)}, None, None, "decision")
        async with pool.acquire() as conn:
            await doc_repo.update_document_status(
                conn, tenant_id=tenant_id, document_id=document_id, status="failed",
            )
        await _complete_session(ctx, "fail", tokens_in, tokens_out, f"decision: {exc}")
        return

    tokens_in += dec_res.usage.tokens_in
    tokens_out += dec_res.usage.tokens_out
    await _finish_step(
        ctx, run_id, "success",
        {"tool_content": dec_res.tool_content, "tool_output": dec_res.tool_output},
        dec_res.usage.tokens_in, dec_res.usage.tokens_out, "decision",
    )
    async with pool.acquire() as conn:
        await doc_repo.insert_decision(
            conn,
            tenant_id=tenant_id, document_id=document_id,
            session_id=session_id, pipeline_run_id=run_id,
            tool_content=dec_res.tool_content, tool_output=dec_res.tool_output,
        )
        await doc_repo.update_document_status(
            conn, tenant_id=tenant_id, document_id=document_id, status="completed",
        )

    await _complete_session(ctx, "success", tokens_in, tokens_out, None)


async def run_rule_book_pipeline(
    *,
    tenant_id: UUID,
    document_id: UUID,
    session_id: UUID,
    storage_key: str,
    mime_type: str,
    original_name: str,
) -> None:
    """Two steps for rule books: parsing + extraction. No validation / decision."""
    set_correlation_id(f"rb-sess-{session_id.hex[:12]}")
    ctx = StepContext(
        tenant_id=tenant_id, document_id=document_id,
        session_id=session_id, type="rule_book",
    )
    await get_bus().publish(session_id, {"event": "session_started", "type": "rule_book"})

    pool = get_pool()
    tokens_in = 0
    tokens_out = 0

    # step 1: parsing
    run_id = await _start_step(ctx, "parsing", "manual")
    try:
        storage = get_storage()
        data = await storage.get(storage_key)
        pre = await preprocess(data, mime_type, original_name)
        parsing_response = {
            "source_kind": pre.source_kind,
            "page_count": pre.page_count,
            "text_len": len(pre.text),
            "image_count": len(pre.images_b64),
            "notes": pre.notes,
            "parsed_text": _truncate_parsed_text(pre.text),
        }
    except Exception as exc:
        logger.exception("rb_parsing_failed")
        await _finish_step(ctx, run_id, "fail", {"error": str(exc)}, None, None, "parsing")
        async with pool.acquire() as conn:
            await doc_repo.update_document_status(
                conn, tenant_id=tenant_id, document_id=document_id, status="failed",
            )
        await _complete_session(ctx, "fail", tokens_in, tokens_out, f"parsing: {exc}")
        return
    await _finish_step(ctx, run_id, "success", parsing_response, None, None, "parsing")

    async with pool.acquire() as conn:
        await doc_repo.update_document_status(
            conn, tenant_id=tenant_id, document_id=document_id, status="extracting",
        )

    # step 2: extraction (llm)
    run_id = await _start_step(ctx, "extraction", "llm")
    try:
        rb_res = await extract_rule_book(pre)
    except Exception as exc:
        logger.exception("rb_extraction_failed")
        await _finish_step(ctx, run_id, "fail", {"error": str(exc)}, None, None, "extraction")
        async with pool.acquire() as conn:
            await doc_repo.update_document_status(
                conn, tenant_id=tenant_id, document_id=document_id, status="failed",
            )
        await _complete_session(ctx, "fail", tokens_in, tokens_out, f"extraction: {exc}")
        return

    tokens_in += rb_res.usage.tokens_in
    tokens_out += rb_res.usage.tokens_out
    await _finish_step(
        ctx, run_id, "success",
        {"tool_content": rb_res.tool_content, "tool_output": rb_res.tool_output},
        rb_res.usage.tokens_in, rb_res.usage.tokens_out, "extraction",
    )

    rules_as_dicts = [r.model_dump(mode="json") for r in rb_res.output.rules]
    async with pool.acquire() as conn:
        await doc_repo.insert_extraction(
            conn,
            tenant_id=tenant_id, document_id=document_id,
            session_id=session_id, pipeline_run_id=run_id,
            tool_content=rb_res.tool_content, tool_output=rb_res.tool_output,
        )
        await doc_repo.set_extracted_rules(
            conn, tenant_id=tenant_id, document_id=document_id, rules=rules_as_dicts,
        )
        await doc_repo.update_document_status(
            conn, tenant_id=tenant_id, document_id=document_id, status="completed",
        )
        await doc_repo.activate_rule_book(
            conn, tenant_id=tenant_id, document_id=document_id,
        )

    await _complete_session(ctx, "success", tokens_in, tokens_out, None)


_PARSED_TEXT_MAX_CHARS = 20000


def _truncate_parsed_text(text: str) -> str:
    if not text:
        return ""
    if len(text) <= _PARSED_TEXT_MAX_CHARS:
        return text
    return text[:_PARSED_TEXT_MAX_CHARS] + f"\n\n…[truncated {len(text) - _PARSED_TEXT_MAX_CHARS} chars]"


def _rules_from_extracted(raw: Any) -> list[tuple[str, RuleSpec]]:
    """Turn the JSONB `extracted_rules` blob into the list of (rule_id, RuleSpec)
    the validator expects. rule_ids are synthetic indices — stable within a
    rule book run."""
    if raw is None:
        return []
    import json as _json
    if isinstance(raw, str):
        raw = _json.loads(raw)
    out: list[tuple[str, RuleSpec]] = []
    for i, item in enumerate(raw):
        out.append((
            f"rule-{i}",
            RuleSpec(
                field_name=item["field_name"],
                rule_type=item["rule_type"],
                spec=item.get("spec", {}),
                severity=Severity(item["severity"]),
                description=item.get("description"),
            ),
        ))
    return out
