from functools import lru_cache

from app.assistant.chat import ChatService
from app.assistant.llm.openai_provider import OpenAIProvider, make_client
from app.assistant.llm.router import FallbackLLM
from app.assistant.sandbox import OpenAISandbox
from app.config import get_settings
from app.db import SessionLocal


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    client = make_client(settings.openai_api_key)
    llm = FallbackLLM(
        [
            OpenAIProvider(client, settings.llm_primary_model),
            OpenAIProvider(client, settings.llm_fallback_model),
        ]
    )
    return ChatService(llm, SessionLocal, OpenAISandbox(client) if settings.openai_api_key else None)
