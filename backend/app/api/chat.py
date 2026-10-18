"""API ассистента: диалоги, стрим ответа (SSE), остановка, подтверждение действий, файлы, память."""

import asyncio
import json
import logging
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.assistant import memory
from app.assistant.chat import ChatService, confirm_action, message_to_dict, reject_action
from app.assistant.factory import get_chat_service
from app.assistant.quota import check_chat_quota
from app.config import get_settings
from app.deps import CurrentUser, SessionDep
from app.errors import DomainError, NotFound
from app.models import ChatFile, Conversation, Message
from app.schemas import DbId
from app.web import Id

router = APIRouter(prefix="/api/chat", tags=["assistant"])
log = logging.getLogger(__name__)

ChatDep = Annotated[ChatService, Depends(get_chat_service)]

# Активные ходы: conversation_id -> событие остановки. Один процесс API; при нескольких
# воркерах это нужно вынести в Redis pub/sub (см. README).
ACTIVE_TURNS: dict[int, asyncio.Event] = {}

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_UPLOADS = {".csv", ".xlsx", ".txt", ".tsv", ".json"}


class ConversationOut(BaseModel):
    id: int
    title: str
    updated_at: str


class SendIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    file_ids: list[DbId] = Field(default_factory=list, max_length=5)


class FactIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


async def _own_conversation(session, user_id: int, conversation_id: int) -> Conversation:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise NotFound("Диалог не найден.")
    return conv


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(session: SessionDep, user: CurrentUser):
    rows = await session.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(100)
    )
    return [ConversationOut(id=c.id, title=c.title, updated_at=c.updated_at.isoformat()) for c in rows]


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(session: SessionDep, user: CurrentUser):
    conv = Conversation(user_id=user.id)
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return ConversationOut(id=conv.id, title=conv.title, updated_at=conv.updated_at.isoformat())


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: Id, session: SessionDep, user: CurrentUser):
    conv = await _own_conversation(session, user.id, conversation_id)
    await session.delete(conv)
    await session.commit()
    return {"ok": True}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: Id, session: SessionDep, user: CurrentUser) -> list[dict[str, Any]]:
    await _own_conversation(session, user.id, conversation_id)
    rows = await session.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    )
    return [await message_to_dict(session, m) for m in rows]


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: Id, body: SendIn, session: SessionDep, user: CurrentUser, chat: ChatDep
):
    """Отправить вопрос. Ответ — поток Server-Sent Events: start, delta, tool, code, action, file, model, done."""
    await _own_conversation(session, user.id, conversation_id)
    if not get_settings().openai_api_key:
        raise DomainError(
            "Ассистент не настроен: укажите OPENAI_API_KEY в файле .env и перезапустите docker compose."
        )
    await check_chat_quota(
        session,
        user.id,
        per_user_hourly=get_settings().chat_user_hourly_limit,
        total_daily=get_settings().chat_daily_limit,
    )
    if conversation_id in ACTIVE_TURNS:
        raise DomainError("Ассистент ещё отвечает в этом диалоге. Дождитесь ответа или нажмите «Остановить».")
    stop = asyncio.Event()
    ACTIVE_TURNS[conversation_id] = stop
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def runner() -> None:
        try:
            await chat.run_turn(
                user=user,
                conversation_id=conversation_id,
                text=body.text,
                file_ids=body.file_ids,
                emit=emit,
                stop=stop,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("turn crashed")
            await queue.put(
                {"type": "error", "message": getattr(exc, "message", "Не удалось получить ответ.")}
            )
        finally:
            ACTIVE_TURNS.pop(conversation_id, None)
            await queue.put(None)

    task = asyncio.create_task(runner())

    async def stream():
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield _sse(event)
        finally:
            # Клиент закрыл соединение (или нажал «Остановить» и оборвал fetch): останавливаем ход,
            # частичный ответ сохранится с пометкой «прерван».
            if not task.done():
                stop.set()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/stop")
async def stop_turn(conversation_id: Id, session: SessionDep, user: CurrentUser):
    await _own_conversation(session, user.id, conversation_id)
    event = ACTIVE_TURNS.get(conversation_id)
    if event:
        event.set()
    return {"stopping": bool(event)}


@router.post("/actions/{action_id}/confirm")
async def confirm(action_id: Id, session: SessionDep, user: CurrentUser):
    action = await confirm_action(session, user, action_id)
    return {"id": action.id, "status": action.status, "result": action.result}


@router.post("/actions/{action_id}/reject")
async def reject(action_id: Id, session: SessionDep, user: CurrentUser):
    action = await reject_action(session, user, action_id)
    return {"id": action.id, "status": action.status}


@router.post("/conversations/{conversation_id}/files")
async def upload_file(
    conversation_id: Id, session: SessionDep, user: CurrentUser, file: UploadFile = File(...)
):
    await _own_conversation(session, user.id, conversation_id)
    name = (file.filename or "file").replace("\x00", "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:200]
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_UPLOADS:
        raise DomainError("Можно загрузить CSV, XLSX, TXT, TSV или JSON.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise DomainError("Файл больше 5 МБ.")
    row = ChatFile(
        conversation_id=conversation_id,
        user_id=user.id,
        direction="upload",
        filename=name,
        mime=file.content_type or "application/octet-stream",
        data=data,
    )
    session.add(row)
    await session.commit()
    return {"id": row.id, "filename": row.filename, "mime": row.mime}


@router.get("/files/{file_id}")
async def download_file(file_id: Id, session: SessionDep, user: CurrentUser):
    f = await session.get(ChatFile, file_id)
    if f is None or f.user_id != user.id:
        raise HTTPException(404, "Файл не найден.")
    disposition = "inline" if f.mime.startswith("image/") else "attachment"
    return Response(
        content=f.data,
        media_type=f.mime,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(f.filename)}"},
    )


# ---------- память ----------


@router.get("/memory")
async def list_memory(session: SessionDep, user: CurrentUser):
    facts = await memory.list_facts(session, user.id)
    return [{"id": f.id, "text": f.text, "created_at": f.created_at.isoformat()} for f in facts]


@router.post("/memory")
async def add_memory(body: FactIn, session: SessionDep, user: CurrentUser):
    f = await memory.add_fact(session, user.id, body.text)
    return {"id": f.id, "text": f.text, "created_at": f.created_at.isoformat()}


@router.delete("/memory/{fact_id}")
async def delete_memory(fact_id: Id, session: SessionDep, user: CurrentUser):
    await memory.delete_fact(session, user.id, fact_id)
    return {"ok": True}


@router.delete("/memory")
async def clear_memory(session: SessionDep, user: CurrentUser):
    from app.models import UserFact

    await session.execute(delete(UserFact).where(UserFact.user_id == user.id))
    await session.commit()
    return {"ok": True}
