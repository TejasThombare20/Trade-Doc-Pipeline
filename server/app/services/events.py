"""In-memory per-session event bus for SSE streaming.

Producers (pipeline nodes) publish step events; consumers (SSE handler)
subscribe by session_id. Events are buffered per subscriber so a late
subscriber still catches up on already-published events.

Scope: single-process dev. A multi-instance deployment would replace this
with Redis pub/sub.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any
from uuid import UUID

from app.core.logging import get_logger

logger = get_logger(__name__)


class SessionBus:
    def __init__(self) -> None:
        self._history: dict[str, list[dict]] = defaultdict(list)
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, session_id: UUID, event: dict[str, Any]) -> None:
        key = str(session_id)
        async with self._lock:
            self._history[key].append(event)
            queues = list(self._subs[key])
        for q in queues:
            await q.put(event)

    async def subscribe(self, session_id: UUID) -> tuple[asyncio.Queue, list[dict]]:
        key = str(session_id)
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            history = list(self._history[key])
            self._subs[key].append(q)
        return q, history

    async def unsubscribe(self, session_id: UUID, q: asyncio.Queue) -> None:
        key = str(session_id)
        async with self._lock:
            self._subs[key] = [x for x in self._subs[key] if x is not q]

    async def close(self, session_id: UUID) -> None:
        """Send a sentinel so subscribers end their streams."""
        await self.publish(session_id, {"event": "closed"})


_bus: SessionBus | None = None


def get_bus() -> SessionBus:
    global _bus
    if _bus is None:
        _bus = SessionBus()
    return _bus


def encode_sse(event: dict[str, Any]) -> bytes:
    """Serialize one event dict as an SSE message."""
    name = event.get("event") or "message"
    data = json.dumps(event)
    return f"event: {name}\ndata: {data}\n\n".encode("utf-8")
