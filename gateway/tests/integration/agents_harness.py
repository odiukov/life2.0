"""Run the agents in-process on Postgres and route gateway A2A calls to them by host name."""

from __future__ import annotations

import base64
from contextlib import AsyncExitStack
from typing import Any
from uuid import UUID

import httpx
from body.composition import build_runtime as body_runtime
from body.main import create_app as body_app
from body.settings import BodySettings
from calendar_agent.composition import build_runtime as calendar_runtime
from calendar_agent.main import create_app as calendar_app
from calendar_agent.settings import CalendarSettings
from calendar_agent.testing import FakeGoogleCalendar, FakeGoogleOAuth
from finance.composition import build_runtime as finance_runtime
from finance.main import create_app as finance_app
from finance.settings import FinanceSettings
from habits.composition import build_runtime as habits_runtime
from habits.main import create_app as habits_app
from habits.settings import HabitsSettings
from medication.composition import build_runtime as medication_runtime
from medication.main import create_app as medication_app
from medication.settings import MedicationSettings
from mood.composition import build_runtime as mood_runtime
from mood.main import create_app as mood_app
from mood.settings import MoodSettings
from nutrition.composition import build_runtime as nutrition_runtime
from nutrition.main import create_app as nutrition_app
from nutrition.settings import NutritionSettings
from recovery.composition import build_runtime as recovery_runtime
from recovery.main import create_app as recovery_app
from recovery.settings import RecoverySettings
from shared.testing import dashboard_golden as g
from shared.testing.fakes import FakeLLM, FakePeerClient, FixedClock, InMemoryVectorMemory
from sleep.composition import build_runtime as sleep_runtime
from sleep.main import create_app as sleep_app
from sleep.settings import SleepSettings
from workout.composition import build_runtime as workout_runtime
from workout.main import create_app as workout_app
from workout.settings import WorkoutSettings

KEY = base64.b64encode(bytes(range(32))).decode()


class NoSync:
    async def refresh(self, user_id: UUID) -> None:
        return None


class HostRouter(httpx.AsyncBaseTransport):
    def __init__(self, apps: dict[str, Any]) -> None:
        self._apps = apps
        self._stack = AsyncExitStack()
        self._transports = {host: httpx.ASGITransport(app=app) for host, app in apps.items()}

    async def __aenter__(self) -> HostRouter:
        for app in self._apps.values():
            await self._stack.enter_async_context(app.router.lifespan_context(app))
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._stack.aclose()
        for transport in self._transports.values():
            await transport.aclose()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self._transports[request.url.host].handle_async_request(request)


def build_apps(rw_dsn: str) -> dict[str, Any]:
    clock = FixedClock(g.FROZEN_NOW)

    def common() -> dict[str, Any]:
        return {
            "llm": FakeLLM(),
            "peers": FakePeerClient(),
            "memory": InMemoryVectorMemory(),
            "clock": clock,
        }

    db = {"database": {"dsn": rw_dsn}}
    return {
        "agent-sleep": sleep_app(sleep_runtime(SleepSettings.model_validate(db), **common())),
        "agent-workout": workout_app(
            workout_runtime(WorkoutSettings.model_validate(db), **common())
        ),
        "agent-nutrition": nutrition_app(
            nutrition_runtime(NutritionSettings.model_validate(db), sync=NoSync(), **common())
        ),
        "agent-body": body_app(body_runtime(BodySettings.model_validate(db), **common())),
        "agent-mood": mood_app(mood_runtime(MoodSettings.model_validate(db), **common())),
        "agent-habits": habits_app(habits_runtime(HabitsSettings.model_validate(db), **common())),
        "agent-recovery": recovery_app(
            recovery_runtime(RecoverySettings.model_validate(db), **common())
        ),
        "agent-medication": medication_app(
            medication_runtime(MedicationSettings.model_validate(db), **common())
        ),
        "agent-finance": finance_app(
            finance_runtime(FinanceSettings.model_validate(db), llm=FakeLLM(), clock=clock)
        ),
        "agent-calendar": calendar_app(
            calendar_runtime(
                CalendarSettings.model_validate({**db, "secrets": {"key": KEY}}),
                google=FakeGoogleCalendar(g.GOOGLE_EVENTS),
                oauth=FakeGoogleOAuth(),
                clock=clock,
            )
        ),
    }
