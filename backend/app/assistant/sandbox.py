"""Контейнер Code Interpreter (OpenAI) для диалога.

Бэкенд сам кладёт в контейнер файлы с данными (собранные сервисным слоем, с учётом прав и уже
с псевдонимами) — модель не получает доступа к базе. Файлы, которые создал код модели, скачиваем
и показываем в чате.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from openai import AsyncOpenAI

log = logging.getLogger(__name__)

CONTAINER_IDLE_MINUTES = 20


@dataclass
class SandboxFile:
    id: str
    path: str
    source: str
    size: int


class Sandbox(Protocol):
    async def ensure(self, container_id: str | None, name: str) -> tuple[str, bool]:
        """Возвращает (container_id, создан_заново)."""
        ...

    async def upload(self, container_id: str, filename: str, data: bytes) -> str: ...

    async def list_files(self, container_id: str) -> list[SandboxFile]: ...

    async def download(self, container_id: str, file_id: str) -> bytes: ...


class SandboxError(Exception):
    pass


class OpenAISandbox:
    def __init__(self, client: AsyncOpenAI):
        self.client = client

    async def ensure(self, container_id: str | None, name: str) -> tuple[str, bool]:
        try:
            if container_id:
                try:
                    info = await self.client.containers.retrieve(container_id, timeout=15)
                    if info.status != "expired":
                        return container_id, False
                except Exception:  # noqa: BLE001 — контейнер удалён или истёк, создаём новый
                    log.info("container %s is gone, creating a new one", container_id)
            created = await self.client.containers.create(
                name=name,
                expires_after={"anchor": "last_active_at", "minutes": CONTAINER_IDLE_MINUTES},
                timeout=20,
            )
            return created.id, True
        except Exception as exc:
            raise SandboxError(str(exc)) from exc

    async def upload(self, container_id: str, filename: str, data: bytes) -> str:
        try:
            created = await self.client.containers.files.create(
                container_id, file=(filename, data), timeout=60
            )
            return created.path
        except Exception as exc:
            raise SandboxError(str(exc)) from exc

    async def list_files(self, container_id: str) -> list[SandboxFile]:
        try:
            page = await self.client.containers.files.list(container_id, limit=100, timeout=20)
            return [SandboxFile(f.id, f.path, f.source, f.bytes) for f in page.data]
        except Exception as exc:
            raise SandboxError(str(exc)) from exc

    async def download(self, container_id: str, file_id: str) -> bytes:
        try:
            resp = await self.client.containers.files.content.retrieve(
                file_id, container_id=container_id, timeout=60
            )
            return resp.content
        except Exception as exc:
            raise SandboxError(str(exc)) from exc
