"""Cross-replica delivery for realtime events.

THE PROBLEM THIS SOLVES
=======================
`Hub` fans out to sockets held by THIS process. That is correct for one worker
and silently wrong for two: a customer connected to replica A never sees the
agent's reply that arrived on replica B. The failure is invisible in testing,
because one worker is the default everywhere — you only meet it in production,
under load, as "support chat sometimes doesn't update".

Together with the connection-budget arithmetic in `core/database.py`, this is
one of the two things that had to exist before the API could run more than one
replica at all.

HOW IT WORKS
============
Every broadcast goes through `fanout.publish()` instead of `hub.broadcast()`.

  * No Redis configured -> straight to the local hub. Identical behaviour to
    before, no new dependency, no new failure mode. This is the single-replica
    path and it stays the default.

  * Redis configured -> published to a channel. EVERY replica, including the
    one that published, receives it and delivers to its own local sockets.
    The publisher does not also deliver locally — that would double-send.

WHY THE ORIGINATOR IS EXCLUDED BY ID
====================================
Typing indicators skip the person typing. In-process that is object identity;
across replicas the `Connection` object does not make the trip, so the id
travels in the envelope instead and each replica filters on it locally.

DELIVERY GUARANTEE: NONE, DELIBERATELY
======================================
Redis pub/sub is fire-and-forget. A replica that is restarting misses whatever
is published in that window, and nothing is replayed. That is acceptable here
and nowhere near acceptable in general — it works ONLY because every message
is persisted to Postgres before it is ever broadcast (see `ticket_gateway`),
so a client that missed a frame re-syncs over REST and loses nothing. Do not
reuse this transport for anything whose only copy is the event itself.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.core.config import get_settings
from app.realtime.hub import Hub, broadcaster as _hub_module_broadcaster, hub as default_hub

logger = logging.getLogger("elizade.realtime")

#: One channel for all rooms. Room fan-out is done in-process on receive, which
#: is cheaper than a channel per ticket: Redis pattern-subscriptions cost more
#: than the negligible filtering here, and a channel per ticket would mean
#: subscribe/unsubscribe churn on every socket open and close.
CHANNEL = "elizade:realtime"


class LocalFanout:
    """Single-replica delivery: straight to the in-process hub."""

    def __init__(self, hub: Hub) -> None:
        self._hub = hub

    async def deliver(
        self, room: str, payload: dict[str, Any], *, exclude_id: str | None = None
    ) -> None:
        await self._hub.broadcast(room, payload, exclude_id=exclude_id)

    async def start(self) -> None:  # nothing to connect to
        return

    async def stop(self) -> None:
        return


class RedisFanout:
    """Multi-replica delivery over Redis pub/sub.

    Publishing and receiving are deliberately separate connections: a
    subscriber connection in Redis cannot issue ordinary commands, so sharing
    one would break the moment anything else needed the client.
    """

    def __init__(self, hub: Hub, url: str) -> None:
        self._hub = hub
        self._url = url
        self._redis: Any = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        import redis.asyncio as aioredis  # noqa: PLC0415 — optional dependency

        self._redis = aioredis.from_url(self._url, decode_responses=True)
        self._task = asyncio.create_task(self._listen())
        logger.info("[REALTIME] cross-replica fan-out via Redis on %s", CHANNEL)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._redis is not None:
            await self._redis.aclose()

    async def _listen(self) -> None:
        """Subscribe and deliver locally, reconnecting forever.

        A dropped Redis connection must not permanently deafen this replica —
        it would keep serving sockets that silently stop receiving anything,
        which is worse than a visible failure.
        """
        backoff = 1
        while True:
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe(CHANNEL)
                backoff = 1
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        frame = json.loads(message["data"])
                        await self._hub.broadcast(
                            frame["room"],
                            frame["payload"],
                            exclude_id=frame.get("excludeId"),
                        )
                    except Exception:  # noqa: BLE001
                        # One malformed or undeliverable frame must not kill
                        # the subscription for every other room.
                        logger.exception("dropping unusable realtime frame")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.warning(
                    "realtime subscription lost; retrying in %ss", backoff, exc_info=True
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def deliver(
        self, room: str, payload: dict[str, Any], *, exclude_id: str | None = None
    ) -> None:
        frame = json.dumps({"room": room, "payload": payload, "excludeId": exclude_id})
        # NOT delivered to the local hub here: this replica is subscribed to the
        # same channel and will receive its own publish, so doing both sends
        # every message twice to everyone on the publishing replica.
        await self._redis.publish(CHANNEL, frame)


def build_fanout(hub: Hub | None = None) -> LocalFanout | RedisFanout:
    """Redis when configured, in-process otherwise."""
    target = hub or default_hub
    url = get_settings().redis_url
    if not url:
        logger.info(
            "[REALTIME] no REDIS_URL — in-process fan-out only. "
            "Correct for one replica; add Redis before scaling out."
        )
        return LocalFanout(target)
    return RedisFanout(target, url)


#: Process-wide, swapped in at startup by the lifespan handler.
fanout: LocalFanout | RedisFanout = build_fanout()


async def publish(
    room: str, payload: dict[str, Any], *, exclude_id: str | None = None
) -> None:
    """The one call sites should use instead of `hub.broadcast`."""
    await fanout.deliver(room, payload, exclude_id=exclude_id)


# The sync seam domain services use (`Broadcaster.publish`) has to cross
# replicas too, so the production singleton is pointed at this module's
# delivery. Done here rather than in `hub` because `hub` must not import this
# module — that would be circular, and would also stop the hub being usable on
# its own, which its tests depend on.
_hub_module_broadcaster.deliver = publish
