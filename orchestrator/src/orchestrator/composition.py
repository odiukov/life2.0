"""The public process: gateway routers + the task chat, one FastAPI app."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from gateway.auth.settings import AuthSettings
from gateway.composition import build_gateway
from gateway.settings import GatewaySettings
from langchain_core.tools import BaseTool
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.adapters.chat_model.factory import LangChainChatModelFactory
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.db.users import SqlUserSettings
from shared.adapters.i18n import JsonTranslator
from shared.observability.logging import configure_logging
from shared.ports.users import UserSettingsRepository

from orchestrator.adapters.a2a import A2APeerAgents
from orchestrator.adapters.db import SqlConsentLookup, SqlHouseholdLookup, chat_repositories
from orchestrator.adapters.documents import PdfDocumentReader
from orchestrator.adapters.http import build_router
from orchestrator.adapters.langgraph.checkpoints import CheckpointPool
from orchestrator.adapters.langgraph.graph import LangGraphChat
from orchestrator.adapters.langgraph.tools import build_tools
from orchestrator.adapters.sync import HttpHealthSync
from orchestrator.adapters.vision import ChatModelImageDescriber
from orchestrator.application.ports import RunContext
from orchestrator.application.post_message import PostMessage
from orchestrator.application.proposals import RecordProposals
from orchestrator.application.resolve_action import ResolveAction
from orchestrator.application.tasks import Tasks
from orchestrator.settings import OrchestratorSettings


def build_app(
    settings: OrchestratorSettings, gateway_settings: GatewaySettings, **overrides: Any
) -> FastAPI:
    """Build the process; supplied resources share the app lifespan and are closed on exit."""
    allowed = {
        "http",
        "gateway",
        "auth",
        "engine",
        "uow",
        "clock",
        "translator",
        "chat_models",
        "skills",
        "peers",
        "proposals",
        "sync",
        "checkpoints",
        "graph",
        "resolve",
        "tasks",
        "post",
        "households",
        "consent",
        "documents",
        "vision",
    }
    if unknown := overrides.keys() - allowed:
        raise TypeError(f"Unknown composition overrides: {', '.join(sorted(unknown))}")
    configure_logging(settings.telemetry)
    auth = overrides.get("auth") or AuthSettings()
    http = overrides.get("http") or httpx.AsyncClient()
    gateway = overrides.get("gateway") or build_gateway(gateway_settings, http=http, auth=auth)
    engine = overrides.get("engine") or create_engine(settings.database)
    uow = overrides.get("uow") or SqlUnitOfWorkFactory(
        engine, {**chat_repositories(), UserSettingsRepository: SqlUserSettings}
    )
    clock = overrides.get("clock") or SystemClock()
    translator = overrides.get("translator") or JsonTranslator.from_dir(settings.i18n_locales_dir)
    chat_models = overrides.get("chat_models") or LangChainChatModelFactory(settings)
    clients = {
        name: A2ASkillClient(url, http, timeout_s=settings.agent_timeout_s)
        for name, url in gateway_settings.agent_urls.items()
    }
    peers = overrides.get("peers") or A2APeerAgents(
        gateway_settings.agent_urls, http, timeout_s=settings.agent_timeout_s
    )
    proposals = overrides.get("proposals") or RecordProposals(
        uow, ttl=timedelta(seconds=settings.action_ttl_s)
    )
    sync = overrides.get("sync") or HttpHealthSync(http, gateway_settings.sync_url)
    checkpoints = overrides.get("checkpoints") or CheckpointPool(
        settings.database.dsn.get_secret_value(), max_size=settings.checkpointer_pool_max
    )

    skills = overrides.get("skills") or clients.__getitem__
    households = overrides.get("households") or SqlHouseholdLookup(engine)
    consent = overrides.get("consent") or SqlConsentLookup(engine)

    def tools(ctx: RunContext, last_user_text: str) -> list[BaseTool]:
        return build_tools(
            ctx,
            last_user_text=last_user_text,
            peers=peers,
            skills=skills,
            proposals=proposals,
            sync=sync,
        )

    graph = overrides.get("graph") or LangGraphChat(
        chat_models, checkpoints, tools, recursion_limit=settings.recursion_limit
    )
    resolve = overrides.get("resolve") or ResolveAction(
        uow=uow, skills=skills, translator=translator, default_locale=settings.default_locale
    )
    tasks = overrides.get("tasks") or Tasks(uow=uow, households=households, graph=graph)
    post = overrides.get("post") or PostMessage(
        uow=uow,
        graph=graph,
        skills=skills,
        documents=overrides.get("documents") or PdfDocumentReader(),
        vision=overrides.get("vision")
        or ChatModelImageDescriber(chat_models, timeout_s=settings.vision_timeout_s),
        resolve=resolve,
        clock=clock,
        translator=translator,
        default_locale=settings.default_locale,
        run_timeout_s=settings.run_timeout_s,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            stack.push_async_callback(http.aclose)
            stack.push_async_callback(engine.dispose)
            stack.push_async_callback(gateway.aclose)
            stack.push_async_callback(checkpoints.close)
            await checkpoints.open()
            await checkpoints.verify_schema()
            yield

    app = FastAPI(title="life-agents", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if auth.env == "dev" else [],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in gateway.routers:
        app.include_router(router)
    app.include_router(build_router(tasks, post, resolve, gateway.authenticate, consent=consent))
    app.state.consent = consent
    return app
