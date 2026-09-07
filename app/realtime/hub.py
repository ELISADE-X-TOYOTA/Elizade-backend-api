"""In-process room hub for WebSocket fan-out.

WHAT THIS IS: a registry of live sockets grouped into rooms, plus a broadcast
that writes to every socket in a room. That is the whole job — authorisation
happens before a socket is ever added, and message persistence happens before
a broadcast is ever requested.

── THE SCALING LIMIT, STATED UP FRONT ──────────────────────────────────────
This fan-out is IN-PROCESS. A broadcast reaches only the clients connected to
*this* worker. The API runs a single uvicorn worker today (see the Dockerfile
CMD — no `--workers`), so that is correct right now and costs nothing.

The moment a second worker or a second instance is added, a customer on worker
A stops seeing an agent's reply from worker B, and the failure is invisible in
testing because one worker is the default everywhere. `Broadcaster` exists as
the seam for that: swap this implementation for one that publishes to Redis
pub/sub and fans out on receive, and nothing above it changes.
────────────────────────────────────────────────────────────────────────────

Sockets are held per-room AND per-connection because the same user legitimately
has several (phone and web console at once), and one dead socket must not stop
delivery to the others.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger("elizade.realtime")


class Sendable(Protocol):
    """The slice of `WebSocket` the hub actually uses.

    Narrow on purpose: tests drive the hub with a fake rather than a real
    socket, and a hub that only needs `send_json` is trivial to fake honestly.
    """

    async def send_json(self, data: Any) -> None: ...


@dataclass(eq=False)
class Connection:
    """One live socket, with the identity that was verified at handshake.

    `eq=False` keeps Python's identity-based `__eq__`/`__hash__`. A generated
    `__eq__` would set `__hash__` to None and make this unusable in the room
    sets — and would be wrong anyway: two sockets from the same user on the
    same ticket are genuinely different connections, not duplicates to merge.
    """

    socket: Sendable
    user_id: str
    #: "customer" or "staff" — decides what this connection may be sent.
    role: str
    rooms: set[str] = field(default_factory=set)


class Hub:
    def __init__(self) -> None:
        self._rooms: dict[str, set[Connection]] = defaultdict(set)
        # Guards the room map. Broadcasts and disconnects interleave freely
        # under load, and mutating a set while iterating it raises.
        self._lock = asyncio.Lock()

    # ── membership ──────────────────────────────────────────────────────

    async def join(self, connection: Connection, room: str) -> None:
        async with self._lock:
            self._rooms[room].add(connection)
            connection.rooms.add(room)

    async def leave(self, connection: Connection, room: str) -> None:
        async with self._lock:
            self._rooms.get(room, set()).discard(connection)
            connection.rooms.discard(room)
            if not self._rooms.get(room):
                self._rooms.pop(room, None)

    async def disconnect(self, connection: Connection) -> None:
        """Remove a socket from every room it joined."""
        async with self._lock:
            for room in list(connection.rooms):
                self._rooms.get(room, set()).discard(connection)
                if not self._rooms.get(room):
                    self._rooms.pop(room, None)
            connection.rooms.clear()

    def room_size(self, room: str) -> int:
        return len(self._rooms.get(room, set()))

    def rooms_for(self, connection: Connection) -> set[str]:
        return set(connection.rooms)

    # ── fan-out ─────────────────────────────────────────────────────────

    async def broadcast(
        self,
        room: str,
        payload: dict[str, Any],
        *,
        exclude: Connection | None = None,
    ) -> int:
        """Send `payload` to every socket in `room`. Returns the count sent.

        `exclude` skips the originator — used for typing indicators, where
        echoing someone's own keystrokes back is pure noise.

        A socket that raises is dropped rather than retried. It has already
        gone away; the client reconnects and re-syncs over REST, which is the
        path that guarantees delivery. Trying harder here would block the
        broadcast on a dead peer.
        """
        async with self._lock:
            targets = [c for c in self._rooms.get(room, set()) if c is not exclude]

        if not targets:
            return 0

        results = await asyncio.gather(
            *(c.socket.send_json(payload) for c in targets),
            return_exceptions=True,
        )

        dead = [c for c, r in zip(targets, results) if isinstance(r, Exception)]
        for connection in dead:
            logger.debug("dropping dead socket for user %s", connection.user_id)
            await self.disconnect(connection)

        return len(targets) - len(dead)


class Broadcaster:
    """The seam between domain code and the transport.

    Domain services call `publish`, which is SYNCHRONOUS and never awaits — it
    is invoked from ordinary request handlers that are not async and must not
    be made async just to announce something. The work is handed to the running
    event loop and the caller carries on.

    Nothing here can fail a request. A reply that was saved but not broadcast
    is a client that refreshes a moment later; a broadcast that rolls back a
    saved reply would be a lost message.
    """

    def __init__(self, hub: Hub) -> None:
        self.hub = hub

    def publish(self, room: str, payload: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop — a script, or a sync test. Nothing is listening anyway.
            logger.debug("no event loop; skipping broadcast to %s", room)
            return
        loop.create_task(self._safe_broadcast(room, payload))

    async def _safe_broadcast(self, room: str, payload: dict[str, Any]) -> None:
        try:
            await self.hub.broadcast(room, payload)
        except Exception:  # noqa: BLE001 — a fire-and-forget task must not die loudly
            logger.exception("broadcast to %s failed", room)


def ticket_room(ticket_id: str) -> str:
    """The one place the room-name format is decided."""
    return f"ticket:{ticket_id}"


#: Process-wide singletons. One hub per worker, which is the whole point.
hub = Hub()
broadcaster = Broadcaster(hub)
