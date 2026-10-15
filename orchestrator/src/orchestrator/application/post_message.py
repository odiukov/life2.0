"""POST /tasks/{id}/messages: one user turn → documents, photos, the fast path or the graph."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, aclosing
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from shared.observability.logging import get_logger
from shared.ports.clock import Clock
from shared.ports.skills import Attachment, SkillCallError, SkillClient, SkillUnavailable
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository, resolve_zone
from shared.skill_ids import Body, Finance

from orchestrator.application.ports import (
    ChatGraph,
    ChatTaskRepository,
    DocumentReader,
    FinalText,
    GraphSession,
    ImageDescriber,
    InvalidHistory,
    NewMessage,
    PendingActionRepository,
    RunContext,
    ToolDone,
    TranscriptRepository,
    UnreadableDocument,
    VisionUnavailable,
)
from orchestrator.application.resolve_action import ResolveAction
from orchestrator.application.routing import Routing
from orchestrator.application.tasks import TaskNotFound
from orchestrator.domain import events as ev
from orchestrator.domain.attachments import (
    MAX_TEXT,
    Upload,
    check_uploads,
    detect_file_kind,
)
from orchestrator.domain.errors import ErrorCode, message_key
from orchestrator.domain.replies import classify_reply
from orchestrator.domain.tasks import title_from

logger = get_logger(__name__)


class EmptyMessage(Exception):
    pass


def _meta(u: Upload) -> dict[str, object]:
    return {
        "kind": "image" if u.is_image else "document",
        "name": u.name,
        "mime": u.mime,
        "size": len(u.data),
    }


@dataclass
class Run:
    """An opened run: its session is held until events() finishes or is cancelled."""

    _owner: PostMessage
    _ctx: RunContext
    _cm: AbstractAsyncContextManager[GraphSession]
    _session: GraphSession
    _text: str
    _uploads: list[Upload]
    _closed: bool = field(default=False, init=False)
    _started: bool = field(default=False, init=False)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._uploads.clear()
        cleanup = asyncio.create_task(self._cm.__aexit__(None, None, None))
        cancelled = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled = True
        cleanup.result()
        if cancelled:
            raise asyncio.CancelledError

    async def events(self) -> AsyncGenerator[dict[str, Any], None]:
        if self._closed or self._started:
            raise RuntimeError("run_already_consumed")
        self._started = True
        try:
            async with aclosing(
                self._owner._run(self._ctx, self._session, self._text, self._uploads)
            ) as events:
                async for event in events:
                    yield event
        finally:
            await self.aclose()


class PostMessage:
    def __init__(
        self,
        *,
        uow: UnitOfWorkFactory,
        graph: ChatGraph,
        skills: Callable[[str], SkillClient],
        documents: DocumentReader,
        vision: ImageDescriber,
        resolve: ResolveAction,
        clock: Clock,
        translator: Translator,
        default_locale: str,
        run_timeout_s: float,
    ) -> None:
        self._uow, self._graph, self._skills = uow, graph, skills
        self._documents, self._vision, self._resolve = documents, vision, resolve
        self._clock, self._tr, self._default, self._timeout = (
            clock,
            translator,
            default_locale,
            run_timeout_s,
        )

    async def start(
        self,
        user_id: UUID,
        task_id: UUID,
        *,
        text: str,
        timezone: str | None,
        uploads: Sequence[Upload],
    ) -> Run:
        text = (text or "").strip()[:MAX_TEXT]
        files = check_uploads(uploads)  # AttachmentRejected propagates
        if not text and not files:
            raise EmptyMessage
        async with self._uow.for_user(user_id) as tx:
            task = await tx.repo(ChatTaskRepository).get(user_id, task_id)
            settings = await tx.repo(UserSettingsRepository).get(user_id)
        if task is None:
            raise TaskNotFound
        zone = resolve_zone(timezone) if timezone else settings.timezone
        ctx = RunContext(
            user_id,
            task_id,
            task.household_id,
            task.lead_agent,
            zone,
            settings.locale or self._default,
            self._clock.now(),
        )
        cm = self._graph.session(ctx, text)
        session = await cm.__aenter__()  # TaskBusy propagates before anything is streamed
        try:
            async with self._uow.for_user(user_id) as tx:
                if await tx.repo(ChatTaskRepository).get(user_id, task_id) is None:
                    raise TaskNotFound
        except BaseException:
            await cm.__aexit__(None, None, None)
            raise
        return Run(self, ctx, cm, session, text, files)

    def _t(self, ctx: RunContext, key: str, **params: object) -> str:
        return self._tr.t(key, ctx.locale, **params)

    async def _run(
        self, ctx: RunContext, session: GraphSession, text: str, uploads: list[Upload]
    ) -> AsyncGenerator[dict[str, Any], None]:
        run_id, message_id = str(uuid4()), str(uuid4())
        yield ev.run_started(str(ctx.task_id), run_id)
        yield ev.text_start(message_id)
        routing, reply, action_meta = Routing(), [], None
        routed = consulted_sent = False
        emitted_primary: str | None = None
        document_context: tuple[str, str] | None = None
        try:
            try:
                async with asyncio.timeout(self._timeout):
                    async with self._uow.for_user(ctx.user_id) as tx:
                        await tx.repo(TranscriptRepository).append(
                            ctx.user_id,
                            ctx.task_id,
                            NewMessage("user", text, attachments=[_meta(u) for u in uploads]),
                        )
                        task = await tx.repo(ChatTaskRepository).get(ctx.user_id, ctx.task_id)
                        if task is not None and task.title is None and text:
                            await tx.repo(ChatTaskRepository).update(
                                ctx.user_id, ctx.task_id, {"title": title_from(text)}
                            )
                    # Documents first: their summaries are part of this reply.
                    for upload in (u for u in uploads if u.is_pdf):
                        line, agent = await self._import(ctx, upload)
                        if agent:
                            routing.observe(ToolDone(agent))
                        if not routed or emitted_primary != routing.primary:
                            yield ev.agent_routed(routing.primary)
                            emitted_primary = routing.primary
                            routed = True
                        reply.append(line + "\n")
                        yield ev.text_delta(message_id, line + "\n")
                    if reply:
                        document_context = (
                            "\n".join(u.name for u in uploads if u.is_pdf),
                            "".join(reply),
                        )
                        await session.append(*document_context)
                    photos: list[str] = []
                    for upload in (u for u in uploads if u.is_image):
                        try:
                            photos.append(
                                f'[Photo "{upload.name}": {await self._vision.describe(upload, text, ctx.locale)}]'
                            )
                        except VisionUnavailable:
                            yield ev.run_error(
                                ErrorCode.UNSUPPORTED_ATTACHMENT,
                                self._t(ctx, message_key(ErrorCode.UNSUPPORTED_ATTACHMENT)),
                            )
                    if text and not uploads:
                        async with self._uow.for_user(ctx.user_id) as tx:
                            pending = await tx.repo(PendingActionRepository).pending(
                                ctx.user_id, ctx.task_id
                            )
                        decision = classify_reply(text) if pending else None
                        if pending and decision:
                            routing.observe(
                                ToolDone(pending.agent)
                            )  # the reply carries the action's agent tag
                            yield ev.agent_routed(routing.primary)
                            emitted_primary = routing.primary
                            routed = True
                            result = await self._resolve(
                                ctx.user_id, ctx.task_id, pending.id, decision, session=session
                            )
                            yield ev.action_resolved(str(pending.id), result.status, result.message)
                            reply.append(result.message)
                            yield ev.text_delta(message_id, result.message)
                            text = ""  # handled; no graph run
                    graph_input = "\n\n".join(part for part in (text, *photos) if part)
                    if graph_input:
                        for attempt in range(2):
                            try:
                                async with aclosing(session.run(graph_input)) as graph_events:
                                    async for event in graph_events:
                                        if isinstance(event, ToolDone):
                                            routing.observe(event)
                                            if event.failed:
                                                yield ev.run_error(
                                                    ErrorCode.AGENT_UNAVAILABLE,
                                                    self._t(
                                                        ctx,
                                                        message_key(ErrorCode.AGENT_UNAVAILABLE),
                                                    ),
                                                )
                                            if event.proposal_id is not None:
                                                action_meta = await self._proposed(
                                                    ctx, event.proposal_id
                                                )
                                                if action_meta:
                                                    yield ev.action_proposed(
                                                        action_meta["id"],
                                                        action_meta["summary"],
                                                        action_meta["expires_at"],
                                                    )
                                        elif isinstance(event, FinalText):
                                            if not routed or emitted_primary != routing.primary:
                                                yield ev.agent_routed(routing.primary)
                                                emitted_primary = routing.primary
                                                routed = True
                                            reply.append(event.text)
                                            yield ev.text_delta(message_id, event.text)
                                            if routing.consulted and not consulted_sent:
                                                yield ev.agent_consulted(routing.consulted)
                                                consulted_sent = True
                                break
                            except InvalidHistory:
                                if attempt:
                                    raise
                                await session.reset()
                                if document_context is not None:
                                    await session.append(*document_context)
                                if not routed or emitted_primary != routing.primary:
                                    yield ev.agent_routed(routing.primary)
                                    emitted_primary = routing.primary
                                    routed = True
                                notice = self._t(ctx, "chat.notices.history_reset")
                                reply.append(notice)
                                yield ev.text_delta(message_id, notice)
            except TimeoutError:
                yield ev.run_error(ErrorCode.TIMEOUT, self._t(ctx, message_key(ErrorCode.TIMEOUT)))
            except Exception as exc:
                logger.error("chat_run_failed", error_type=type(exc).__name__)
                yield ev.run_error(
                    ErrorCode.INTERNAL, self._t(ctx, message_key(ErrorCode.INTERNAL))
                )
            if not routed or emitted_primary != routing.primary:
                yield ev.agent_routed(routing.primary)
                emitted_primary = routing.primary
        finally:
            # Finish the one transcript write before the session releases its task lock.
            saving = asyncio.create_task(self._save_reply(ctx, routing, reply, action_meta))
            cancelled = False
            while not saving.done():
                try:
                    await asyncio.shield(saving)
                except asyncio.CancelledError:
                    cancelled = True
            saved = saving.result()
            if cancelled:
                raise asyncio.CancelledError
        if not saved:
            yield ev.run_error(ErrorCode.INTERNAL, self._t(ctx, message_key(ErrorCode.INTERNAL)))
        yield ev.text_end(message_id)
        yield ev.run_finished(str(ctx.task_id), run_id)

    async def _save_reply(
        self,
        ctx: RunContext,
        routing: Routing,
        reply: list[str],
        action_meta: dict[str, str] | None,
    ) -> bool:
        try:
            async with self._uow.for_user(ctx.user_id) as tx:
                if reply or action_meta:
                    await tx.repo(TranscriptRepository).append(
                        ctx.user_id,
                        ctx.task_id,
                        NewMessage(
                            "assistant",
                            "".join(reply),
                            agent=routing.primary if routing.primary != "main" else None,
                            consulted=routing.consulted,
                            action={
                                "id": action_meta["id"],
                                "summary": action_meta["summary"],
                                "status": "pending",
                            }
                            if action_meta
                            else None,
                        ),
                    )
                await tx.repo(ChatTaskRepository).touch(ctx.user_id, ctx.task_id)
        except Exception as exc:
            logger.error("chat_transcript_failed", error_type=type(exc).__name__)
            return False
        return True

    async def _proposed(self, ctx: RunContext, action_id: UUID) -> dict[str, str] | None:
        async with self._uow.for_user(ctx.user_id) as tx:
            action = await tx.repo(PendingActionRepository).pending(ctx.user_id, ctx.task_id)
        if action is None or action.id != action_id:
            return None
        return {
            "id": str(action.id),
            "summary": action.summary,
            "expires_at": action.expires_at.isoformat(),
        }

    async def _import(self, ctx: RunContext, upload: Upload) -> tuple[str, str | None]:
        try:
            kind = detect_file_kind(self._documents.text(upload.data), ctx.lead_agent, upload.name)
        except UnreadableDocument:
            return self._t(ctx, "chat.files.unreadable", name=upload.name), None
        if kind == "unknown":
            return self._t(ctx, "chat.files.unsupported", name=upload.name), None
        agent, skill, params = (
            ("finance", Finance.IMPORT_STATEMENT, {})
            if kind == "payoneer"
            else ("body", Body.IMPORT_VIHEALTH, {"save_profile": True})
        )
        try:
            reply = await self._skills(agent).call(
                skill_id=skill,
                user_id=ctx.user_id,
                params=params,
                attachments=[Attachment(upload.name, upload.mime, upload.data)],
            )
        except (SkillCallError, SkillUnavailable) as exc:
            logger.warning("chat_import_failed", agent=agent, error_type=type(exc).__name__)
            return self._t(ctx, "chat.files.failed", name=upload.name), agent
        return reply.text, agent
