import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from a2a.types import Message, Part, Role, TextPart
from shared.adapters import peers as peers_module
from shared.adapters import vector as vector_module
from shared.adapters.peers import LEGACY_UNAVAILABLE, A2APeerClient
from shared.adapters.scheduler import ApschedulerScheduler
from shared.adapters.vector import QdrantVectorMemory


async def test_peer_client_keeps_only_real_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def fake_fetch(
        registry: Any, names: Any, *, needed: Any, user_id: Any, for_date: Any
    ) -> dict[str, str]:
        seen.update(
            registry=registry, names=names, needed=needed, user_id=user_id, for_date=for_date
        )
        return {"workout": "ran 5k", "sleep": "(данные недоступны)", "mood": "   "}

    monkeypatch.setattr(peers_module, "fetch_peer_artifacts", fake_fetch)
    client = A2APeerClient({"workout": "http://w/", "sleep": "http://s/", "mood": "http://m/"})
    uid = UUID("00000000-0000-0000-0000-000000000001")
    wanted = {"workout": "analyze_workout", "sleep": "analyze_sleep", "mood": "analyze_mood"}
    got = await client.fetch_artifacts(user_id=uid, wanted=wanted, for_date=date(2026, 10, 12))
    assert got == {"workout": "ran 5k"}
    assert seen == {
        "registry": {
            "workout": {"url": "http://w/"},
            "sleep": {"url": "http://s/"},
            "mood": {"url": "http://m/"},
        },
        "names": wanted,
        "needed": set(wanted),
        "user_id": str(uid),
        "for_date": "2026-10-12",
    }
    assert LEGACY_UNAVAILABLE == "(данные недоступны)"


async def test_peer_client_skips_empty_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(*_: Any, **__: Any) -> dict[str, str]:
        pytest.fail("An empty request must not call peers")

    monkeypatch.setattr(peers_module, "fetch_peer_artifacts", forbidden)
    assert await A2APeerClient({}).fetch_artifacts(user_id=uuid4(), wanted={}) == {}


@pytest.mark.parametrize(
    "error", [ConnectionError("private message"), TimeoutError("private output")]
)
async def test_peer_client_backend_failures_are_private(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    class Logger:
        def warning(self, event: str, **fields: Any) -> None:
            events.append((event, fields))

    async def boom(*_: Any, **__: Any) -> dict[str, str]:
        raise error

    monkeypatch.setattr(peers_module, "fetch_peer_artifacts", boom)
    monkeypatch.setattr(peers_module, "logger", Logger())
    client = A2APeerClient({"workout": "http://w/"})
    assert (
        await client.fetch_artifacts(user_id=uuid4(), wanted={"workout": "analyze_workout"}) == {}
    )
    assert events == [("peer_fetch_failed", {"error_type": type(error).__name__})]


async def test_peer_client_propagates_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def cancelled(*_: Any, **__: Any) -> dict[str, str]:
        raise asyncio.CancelledError

    monkeypatch.setattr(peers_module, "fetch_peer_artifacts", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await A2APeerClient({"workout": "http://w/"}).fetch_artifacts(
            user_id=uuid4(), wanted={"workout": "analyze_workout"}
        )


async def test_peer_client_has_a_wall_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    cancelled = asyncio.Event()

    async def stalled(*_: Any, **__: Any) -> dict[str, str]:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return {}

    monkeypatch.setattr(peers_module, "fetch_peer_artifacts", stalled)
    monkeypatch.setattr(peers_module, "PEER_TIMEOUT_S", 0.01)
    async with asyncio.timeout(1):
        got = await A2APeerClient({"sleep": "http://slow/"}).fetch_artifacts(
            user_id=uuid4(), wanted={"sleep": "analyze_sleep"}
        )
    assert got == {}
    assert cancelled.is_set()


async def test_default_peer_registry_is_used_and_explicit_empty_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        peers_module,
        "default_peer_registry",
        lambda: {"sleep": {"url": "http://sleep/"}},
    )
    registries = []

    async def fetch(registry: Any, *_: Any, **__: Any) -> dict[str, str]:
        registries.append(registry)
        return {}

    monkeypatch.setattr(peers_module, "fetch_peer_artifacts", fetch)
    for client in (A2APeerClient(), A2APeerClient({})):
        await client.fetch_artifacts(user_id=uuid4(), wanted={"sleep": "analyze_sleep"})
    assert registries == [{"sleep": {"url": "http://sleep/"}}, {}]


async def test_peer_legacy_calls_are_depth_one_and_failed_peers_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[Message] = []
    uid = uuid4()

    class Client:
        async def send_message(self, message: Message) -> Any:
            messages.append(message)
            yield Message(
                role=Role.agent,
                parts=[Part(root=TextPart(text="slept 8h"))],
                message_id="reply",
            )

    async def get_client(url: str) -> Client:
        if url == "http://slow/":
            raise TimeoutError("slow")
        if url == "http://down/":
            raise ConnectionError("down")
        return Client()

    monkeypatch.setattr(peers_module, "_get_client", get_client)
    client = A2APeerClient(
        {"sleep": "http://sleep/", "mood": "http://slow/", "body": "http://down/"}
    )
    got = await client.fetch_artifacts(
        user_id=uid,
        wanted={"sleep": "analyze_sleep", "mood": "analyze_mood", "body": "analyze_body"},
        for_date=date(2026, 10, 12),
    )
    assert got == {"sleep": "slept 8h"}
    assert len(messages) == 1
    assert messages[0].metadata == {
        "skillId": "analyze_sleep",
        "is_peer_call": True,
        "user_id": str(uid),
        "for_date": "2026-10-12",
    }


async def test_vector_memory_maps_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    stored: dict[str, Any] = {}

    async def fake_upsert(**kwargs: Any) -> None:
        stored.update(kwargs)

    async def fake_search(
        user_id: Any, query: str, limit: int = 5, agent_ids: Any = None
    ) -> list[dict[str, Any]]:
        stored["search"] = (user_id, query, limit, agent_ids)
        return [
            {
                "text": "oats",
                "agent_id": "nutrition",
                "user_id": "x",
                "skill": "log_meal",
                "count": 2,
            }
        ]

    monkeypatch.setattr(vector_module, "_upsert", fake_upsert)
    monkeypatch.setattr(vector_module, "_search", fake_search)
    memory = QdrantVectorMemory()
    uid = uuid4()
    metadata = {"skill": "log_meal"}
    await memory.upsert(user_id=uid, agent="nutrition", key="k1", text="oats", metadata=metadata)
    assert stored["user_id"] == uid
    assert stored["agent_id"] == "nutrition"
    assert stored["id_"] == f'["{uid}","nutrition","k1"]'
    assert stored["text"] == "oats"
    assert stored["metadata"] == metadata
    assert stored["metadata"] is not metadata
    found = await memory.search(user_id=uid, query="breakfast", limit=3, agents=["nutrition"])
    assert found[0].text == "oats"
    assert found[0].agent == "nutrition"
    assert found[0].metadata == {"skill": "log_meal", "count": "2"}
    assert stored["search"] == (uid, "breakfast", 3, ["nutrition"])


async def test_vector_metadata_cannot_override_reserved_payload_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: dict[str, Any] = {}

    async def upsert(**kwargs: Any) -> None:
        stored.update(kwargs)

    monkeypatch.setattr(vector_module, "_upsert", upsert)
    metadata = {
        "user_id": "other",
        "agent_id": "other",
        "text": "other",
        "source": "chat",
        "skill": "log_meal",
    }
    await QdrantVectorMemory().upsert(
        user_id=uuid4(), agent="nutrition", key="k1", text="oats", metadata=metadata
    )
    assert stored["metadata"] == {"source": "chat", "skill": "log_meal"}
    assert metadata["text"] == "other"


async def test_vector_legacy_roundtrip_isolates_users_agents_and_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points: dict[int, Any] = {}

    class Qdrant:
        async def get_collections(self) -> Any:
            return SimpleNamespace(collections=[SimpleNamespace(name="health_memories")])

        async def create_payload_index(self, **_: Any) -> None:
            pass

        async def upsert(self, *, collection_name: str, points: list[Any]) -> None:
            stored_points.update({point.id: point for point in points})

        async def query_points(self, *, query_filter: Any, **_: Any) -> Any:
            def matches(point: Any) -> bool:
                for condition in query_filter.must:
                    value = point.payload[condition.key]
                    match = condition.match
                    if hasattr(match, "value") and value != match.value:
                        return False
                    if hasattr(match, "any") and value not in match.any:
                        return False
                return True

            return SimpleNamespace(
                points=[point for point in stored_points.values() if matches(point)]
            )

    stored_points = points
    qdrant = Qdrant()

    async def embed(*_: Any, **__: Any) -> list[float]:
        return [0.0] * 768

    monkeypatch.setattr(vector_module, "_get_client", lambda: qdrant)
    monkeypatch.setattr(vector_module, "_embed", embed)
    memory = QdrantVectorMemory()
    alice, bob = uuid4(), uuid4()
    for user, agent, key, text in (
        (alice, "nutrition", "same", "oats"),
        (bob, "nutrition", "same", "eggs"),
        (alice, "sleep", "same", "8 hours"),
        (alice, "nutrition", "second", "rice"),
    ):
        await memory.upsert(
            user_id=user, agent=agent, key=key, text=text, metadata={"source": "chat"}
        )
    assert len(points) == 4
    await memory.upsert(
        user_id=alice, agent="nutrition", key="same", text="updated oats", metadata={}
    )
    assert len(points) == 4
    alice_meals = await memory.search(user_id=alice, query="food", limit=5, agents=["nutrition"])
    assert [item.text for item in alice_meals] == ["updated oats", "rice"]
    bob_meals = await memory.search(user_id=bob, query="food", limit=5, agents=["nutrition"])
    assert [item.text for item in bob_meals] == ["eggs"]
    alice_sleep = await memory.search(user_id=alice, query="sleep", limit=5, agents=["sleep"])
    assert [item.text for item in alice_sleep] == ["8 hours"]


async def test_vector_backend_failures_are_private_and_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    class Logger:
        def warning(self, event: str, **fields: Any) -> None:
            events.append((event, fields))

    async def boom(*_: Any, **__: Any) -> Any:
        raise ConnectionError("private query and memory")

    monkeypatch.setattr(vector_module, "_upsert", boom)
    monkeypatch.setattr(vector_module, "_search", boom)
    monkeypatch.setattr(vector_module, "logger", Logger())
    memory = QdrantVectorMemory()
    assert (
        await memory.upsert(
            user_id=uuid4(), agent="nutrition", key="k", text="private", metadata={}
        )
        is None
    )
    assert await memory.search(user_id=uuid4(), query="private", limit=3) == []
    assert events == [
        ("vector_upsert_failed", {"error_type": "ConnectionError"}),
        ("vector_search_failed", {"error_type": "ConnectionError"}),
    ]


async def test_vector_propagates_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def cancelled(*_: Any, **__: Any) -> Any:
        raise asyncio.CancelledError

    monkeypatch.setattr(vector_module, "_upsert", cancelled)
    monkeypatch.setattr(vector_module, "_search", cancelled)
    memory = QdrantVectorMemory()
    with pytest.raises(asyncio.CancelledError):
        await memory.upsert(user_id=uuid4(), agent="nutrition", key="k", text="oats", metadata={})
    with pytest.raises(asyncio.CancelledError):
        await memory.search(user_id=uuid4(), query="oats", limit=3)


@pytest.mark.parametrize("agents", [None, []])
async def test_vector_empty_agent_scope_uses_legacy_cross_agent_search(
    monkeypatch: pytest.MonkeyPatch, agents: list[str] | None
) -> None:
    async def search(
        user_id: Any, query: str, *, limit: int, agent_ids: Any
    ) -> list[dict[str, Any]]:
        assert agent_ids is None
        return [{"source": "agent"}]

    monkeypatch.setattr(vector_module, "_search", search)
    found = await QdrantVectorMemory().search(user_id=uuid4(), query="x", limit=5, agents=agents)
    assert found[0].text == ""
    assert found[0].agent == ""
    assert found[0].metadata == {"source": "agent"}


async def test_scheduler_registers_cron_jobs_with_wake_policy() -> None:
    scheduler = ApschedulerScheduler()

    async def job() -> None:
        return None

    scheduler.add_cron("daily", job, hour=9, minute=30, tz="Europe/Lisbon")
    scheduler.add_cron("daily", job, hour=8, minute=15, tz="Europe/Lisbon")
    await scheduler.start()
    try:
        assert scheduler.job_ids() == ["daily"]
        registered = scheduler._scheduler.get_job("daily")
        assert registered.coalesce is True
        assert registered.misfire_grace_time == 21600
        assert str(registered.trigger.timezone) == "Europe/Lisbon"
        next_run = registered.trigger.get_next_fire_time(None, datetime(2026, 7, 1, tzinfo=UTC))
        assert next_run.astimezone(UTC) == datetime(2026, 7, 1, 7, 15, tzinfo=UTC)
    finally:
        await scheduler.shutdown()
        await asyncio.sleep(0)


async def test_apscheduler_interval_job_is_coalesced_and_single_instance() -> None:
    from shared.adapters.scheduler import ApschedulerScheduler

    async def job() -> None:
        return None

    scheduler = ApschedulerScheduler()
    scheduler.add_interval("digest", job, minutes=15)
    await scheduler.start()
    try:
        registered = scheduler._scheduler.get_job("digest")
        assert registered.coalesce is True
        assert registered.max_instances == 1
        assert registered.trigger.interval.total_seconds() == 900
    finally:
        await scheduler.shutdown()


def test_apscheduler_rejects_sub_minute_interval() -> None:
    from shared.adapters.scheduler import ApschedulerScheduler

    async def job() -> None:
        return None

    with pytest.raises(ValueError, match="at least one minute"):
        ApschedulerScheduler().add_interval("x", job, minutes=0)
