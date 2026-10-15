"""The task routes. Errors before streaming are HTTP codes; errors during a run are RunError events."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import aclosing
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from household.adapters.http import Authenticate
from opentelemetry import baggage, context, trace
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask
from starlette.types import Message

from orchestrator.application.ports import ChatTask, ConsentLookup, TaskBusy
from orchestrator.application.post_message import EmptyMessage, PostMessage
from orchestrator.application.resolve_action import ActionNotFound, ResolveAction
from orchestrator.application.tasks import NoHousehold, TaskNotFound, Tasks, UnknownAgent
from orchestrator.domain.attachments import MAX_TOTAL, AttachmentRejected, Upload
from orchestrator.domain.events import sse


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lead_agent: str | None = None
    title: str | None = Field(default=None, max_length=500)


class TaskOut(BaseModel):
    id: UUID
    lead_agent: str | None
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    seq: int
    role: str
    text: str
    agent: str | None
    consulted: list[str]
    attachments: list[dict[str, Any]]
    action: dict[str, Any] | None
    created_at: datetime


class PendingOut(BaseModel):
    id: UUID
    summary: str
    expires_at: datetime


class TaskViewOut(BaseModel):
    task: TaskOut
    messages: list[MessageOut]
    pending_action: PendingOut | None


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["confirm", "reject"]


class ResolutionOut(BaseModel):
    status: str
    message: str


def _task(t: ChatTask) -> TaskOut:
    return TaskOut(
        id=t.id,
        lead_agent=t.lead_agent,
        title=t.title,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def build_router(
    tasks: Tasks,
    post: PostMessage,
    resolve: ResolveAction,
    authenticate: Authenticate,
    *,
    consent: ConsentLookup | None = None,
) -> APIRouter:
    class LimitedUploadRoute(APIRoute):
        def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
            handle = super().get_route_handler()

            async def limited(request: Request) -> Response:
                if request.method != "POST" or not request.url.path.endswith("/messages"):
                    return await handle(request)
                cap = MAX_TOTAL + 1024 * 1024
                length = request.headers.get("content-length")
                if (
                    length is not None
                    and length.isdecimal()
                    and (len(length) > 20 or int(length) > cap)
                ):
                    raise HTTPException(status_code=413, detail="attachment_too_large")
                received = 0

                async def receive() -> Message:
                    nonlocal received
                    message = await request.receive()
                    if message["type"] == "http.request":
                        received += len(message.get("body", b""))
                        if received > cap:
                            raise HTTPException(status_code=413, detail="attachment_too_large")
                    return message

                return await handle(Request(request.scope, receive=receive))

            return limited

    router = APIRouter(prefix="/tasks", tags=["tasks"], route_class=LimitedUploadRoute)
    me = Depends(authenticate)

    def errors(exc: Exception) -> HTTPException:
        match exc:
            case TaskNotFound() | ActionNotFound():
                return HTTPException(status_code=404, detail="not_found")
            case UnknownAgent():
                return HTTPException(status_code=422, detail="unknown_agent")
            case NoHousehold():
                return HTTPException(status_code=422, detail="no_household")
            case TaskBusy():
                return HTTPException(status_code=409, detail="task_busy")
            case AttachmentRejected() as rejected:
                return HTTPException(
                    status_code=413 if rejected.code == "attachment_too_large" else 422,
                    detail=rejected.code,
                )
            case EmptyMessage():
                return HTTPException(status_code=422, detail="empty_message")
        raise exc

    @router.post("", status_code=201, response_model=TaskOut)
    async def open_task(body: TaskIn, user: UUID = me) -> TaskOut:
        try:
            return _task(await tasks.open(user, lead_agent=body.lead_agent, title=body.title))
        except Exception as exc:
            raise errors(exc) from None

    @router.get("", response_model=list[TaskOut])
    async def list_tasks(user: UUID = me) -> list[TaskOut]:
        return [_task(t) for t in await tasks.list(user)]

    @router.get("/{task_id}", response_model=TaskViewOut)
    async def read_task(task_id: UUID, user: UUID = me) -> TaskViewOut:
        try:
            view = await tasks.read(user, task_id)
        except Exception as exc:
            raise errors(exc) from None
        return TaskViewOut(
            task=_task(view.task),
            messages=[
                MessageOut(
                    seq=m.seq,
                    role=m.role,
                    text=m.text,
                    agent=m.agent,
                    consulted=list(m.consulted),
                    attachments=[dict(a) for a in m.attachments],
                    action=dict(m.action) if m.action else None,
                    created_at=m.created_at,
                )
                for m in view.messages
            ],
            pending_action=PendingOut(
                id=view.pending.id, summary=view.pending.summary, expires_at=view.pending.expires_at
            )
            if view.pending
            else None,
        )

    @router.patch("/{task_id}", response_model=TaskOut)
    async def update_task(task_id: UUID, body: TaskIn, user: UUID = me) -> TaskOut:
        try:
            return _task(await tasks.update(user, task_id, body.model_dump(exclude_unset=True)))
        except Exception as exc:
            raise errors(exc) from None

    @router.delete("/{task_id}", status_code=204)
    async def close_task(task_id: UUID, user: UUID = me) -> Response:
        try:
            await tasks.close(user, task_id)
        except Exception as exc:
            raise errors(exc) from None
        return Response(status_code=204)

    @router.post("/{task_id}/messages")
    async def post_message(
        task_id: UUID,
        text: Annotated[str, Form()] = "",
        timezone: Annotated[str | None, Form()] = None,
        attachments: Annotated[list[UploadFile], File()] = [],  # noqa: B006 - FastAPI form default
        user: UUID = me,
    ) -> StreamingResponse:
        uploads = []
        total = 0
        for file in attachments:
            data = await file.read(MAX_TOTAL + 1 - total)
            total += len(data)
            if total > MAX_TOTAL:
                raise HTTPException(status_code=413, detail="attachment_too_large")
            uploads.append(
                Upload(
                    file.filename or "file",
                    (file.content_type or "application/octet-stream").lower(),
                    data,
                )
            )
        bodies_ok = await consent.bodies_ok(user) if consent is not None else False
        try:
            run = await post.start(user, task_id, text=text, timezone=timezone, uploads=uploads)
        except Exception as exc:
            raise errors(exc) from None

        async def stream() -> AsyncIterator[str]:
            token = context.attach(
                baggage.set_baggage("telemetry.bodies_ok", "1" if bodies_ok else "0")
            )
            try:
                with trace.get_tracer(__name__).start_as_current_span(
                    "chat.run",
                    attributes={"langfuse.session.id": str(task_id), "user.id": str(user)},
                ):
                    async with aclosing(run.events()) as events:
                        async for event in events:
                            yield sse(event)
            finally:
                try:
                    await run.aclose()
                finally:
                    context.detach(token)

        return StreamingResponse(
            stream(),
            background=BackgroundTask(run.aclose),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/{task_id}/actions/{action_id}", response_model=ResolutionOut)
    async def resolve_action(
        task_id: UUID, action_id: UUID, body: Decision, user: UUID = me
    ) -> ResolutionOut:
        try:
            view = await tasks.read(user, task_id)
            result = await tasks.with_session(
                user,
                view.task,
                lambda session: resolve(user, task_id, action_id, body.decision, session=session),
            )
        except Exception as exc:
            raise errors(exc) from None
        return ResolutionOut(status=result.status, message=result.message)

    return router
