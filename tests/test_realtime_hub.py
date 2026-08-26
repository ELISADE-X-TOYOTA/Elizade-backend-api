"""The room hub: membership, fan-out, and what happens when a socket dies.

No database and no real sockets — the hub's whole job is bookkeeping, and a
fake `send_json` lets the awkward cases (a peer that raises mid-broadcast, two
devices for one user) be provoked directly instead of hoped for.
"""

import asyncio

import pytest

from app.realtime.hub import Broadcaster, Connection, Hub, ticket_room


class FakeSocket:
    """Records what it was sent. Optionally fails, like a socket that went away."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self.fail = fail

    async def send_json(self, data) -> None:
        if self.fail:
            raise ConnectionError("socket closed")
        self.sent.append(data)


def conn(user_id: str = "u1", role: str = "customer", fail: bool = False):
    socket = FakeSocket(fail=fail)
    return Connection(socket=socket, user_id=user_id, role=role), socket


# ── Membership ───────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_join_puts_a_connection_in_the_room():
    hub = Hub()
    c, _ = conn()
    await hub.join(c, "ticket:1")
    assert hub.room_size("ticket:1") == 1


@pytest.mark.anyio
async def test_leaving_the_last_member_drops_the_room():
    """Rooms must not accumulate — a busy day would leak one entry per ticket."""
    hub = Hub()
    c, _ = conn()
    await hub.join(c, "ticket:1")
    await hub.leave(c, "ticket:1")
    assert hub.room_size("ticket:1") == 0


@pytest.mark.anyio
async def test_one_user_may_hold_several_sockets():
    """Phone and web console at once is normal, not a bug to dedupe away."""
    hub = Hub()
    phone, phone_socket = conn("u1")
    web, web_socket = conn("u1")
    await hub.join(phone, "ticket:1")
    await hub.join(web, "ticket:1")

    await hub.broadcast("ticket:1", {"event": "x"})

    assert len(phone_socket.sent) == 1
    assert len(web_socket.sent) == 1


@pytest.mark.anyio
async def test_disconnect_clears_every_room():
    hub = Hub()
    c, _ = conn()
    await hub.join(c, "ticket:1")
    await hub.join(c, "ticket:2")

    await hub.disconnect(c)

    assert hub.room_size("ticket:1") == 0
    assert hub.room_size("ticket:2") == 0
    assert hub.rooms_for(c) == set()


# ── Fan-out ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_broadcast_reaches_everyone_in_the_room():
    hub = Hub()
    a, sa = conn("a")
    b, sb = conn("b")
    await hub.join(a, "ticket:1")
    await hub.join(b, "ticket:1")

    sent = await hub.broadcast("ticket:1", {"event": "ticket:message_received"})

    assert sent == 2
    assert sa.sent == sb.sent == [{"event": "ticket:message_received"}]


@pytest.mark.anyio
async def test_broadcast_does_not_leak_into_another_room():
    """The isolation the whole authorisation model rests on."""
    hub = Hub()
    mine, my_socket = conn("a")
    theirs, their_socket = conn("b")
    await hub.join(mine, "ticket:1")
    await hub.join(theirs, "ticket:2")

    await hub.broadcast("ticket:1", {"event": "secret"})

    assert my_socket.sent == [{"event": "secret"}]
    assert their_socket.sent == [], "a message reached another ticket's room"


@pytest.mark.anyio
async def test_exclude_skips_the_originator():
    """Typing indicators must not echo your own keystrokes back at you."""
    hub = Hub()
    me, my_socket = conn("a")
    them, their_socket = conn("b")
    await hub.join(me, "ticket:1")
    await hub.join(them, "ticket:1")

    await hub.broadcast("ticket:1", {"event": "typing"}, exclude=me)

    assert my_socket.sent == []
    assert their_socket.sent == [{"event": "typing"}]


@pytest.mark.anyio
async def test_broadcasting_to_an_empty_room_is_harmless():
    hub = Hub()
    assert await hub.broadcast("ticket:nobody", {"event": "x"}) == 0


# ── Dead sockets ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_a_dead_socket_does_not_stop_delivery_to_the_others():
    """One customer losing signal must not silence the agent's console."""
    hub = Hub()
    dead, _ = conn("a", fail=True)
    alive, alive_socket = conn("b")
    await hub.join(dead, "ticket:1")
    await hub.join(alive, "ticket:1")

    sent = await hub.broadcast("ticket:1", {"event": "x"})

    assert alive_socket.sent == [{"event": "x"}]
    assert sent == 1, "the dead socket should not be counted as delivered"


@pytest.mark.anyio
async def test_a_dead_socket_is_evicted():
    hub = Hub()
    dead, _ = conn("a", fail=True)
    await hub.join(dead, "ticket:1")

    await hub.broadcast("ticket:1", {"event": "x"})

    assert hub.room_size("ticket:1") == 0, "a socket that raised was kept"


@pytest.mark.anyio
async def test_concurrent_broadcasts_do_not_corrupt_the_room():
    """Mutating a set while iterating it raises; the lock exists to stop that."""
    hub = Hub()
    members = []
    for i in range(20):
        c, s = conn(f"u{i}")
        await hub.join(c, "ticket:1")
        members.append(s)

    await asyncio.gather(*(hub.broadcast("ticket:1", {"n": i}) for i in range(10)))

    assert all(len(s.sent) == 10 for s in members)


# ── Broadcaster: the sync seam domain code uses ──────────────────────────


@pytest.mark.anyio
async def test_publish_delivers_without_the_caller_awaiting():
    """Domain services are sync; they must not have to become async to announce."""
    hub = Hub()
    c, socket = conn()
    await hub.join(c, "ticket:1")

    Broadcaster(hub).publish("ticket:1", {"event": "x"})
    await asyncio.sleep(0)  # let the scheduled task run
    await asyncio.sleep(0)

    assert socket.sent == [{"event": "x"}]


def test_publish_outside_an_event_loop_is_a_no_op():
    """A management script or sync test has no loop and nothing listening.

    This must not raise — a broadcast is never allowed to fail its caller.
    """
    Broadcaster(Hub()).publish("ticket:1", {"event": "x"})


@pytest.mark.anyio
async def test_publish_survives_a_failing_broadcast():
    """A fire-and-forget task that dies loudly would take out the request."""

    class Exploding(Hub):
        async def broadcast(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    Broadcaster(Exploding()).publish("ticket:1", {"event": "x"})
    await asyncio.sleep(0)
    await asyncio.sleep(0)


# ── Naming ───────────────────────────────────────────────────────────────


def test_room_name_is_derived_not_typed():
    assert ticket_room("abc") == "ticket:abc"
