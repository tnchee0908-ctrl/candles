from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://candles:candles@localhost:5432/candles"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-secret-change-me"
    jwt_ttl_hours: int = 12

    rates_service_url: str = "http://localhost:8101"
    marking_service_url: str = "http://localhost:8102"
    # Таймаут одного HTTP-вызова к сервису маркировки. Мок иногда отвечает через 10 с,
    # поэтому таймаут меньше: такой ответ считаем неудачной попыткой и повторяем.
    marking_timeout_s: float = 5.0
    # Паузы 2, 4, 8 … с, потолок 1 час; 36 попыток ≈ сутки, затем «Не отправлен» и ручной повтор.
    marking_max_attempts: int = 36
    marking_base_delay_s: float = 2.0
    marking_max_delay_s: float = 3600.0

    openai_api_key: str = ""
    llm_primary_model: str = "gpt-4.1-mini"
    llm_fallback_model: str = "gpt-4o-mini"
    # Потолок на один шаг модели (включая Code Interpreter) и на паузу между событиями стрима.
    llm_timeout_s: float = 300.0
    llm_idle_timeout_s: float = 90.0
    llm_max_tool_steps: int = 8
    # Низкая температура: ответы по учётным данным должны быть повторяемыми, а не «творческими».
    llm_temperature: float = 0.2
    # Лимиты сообщений ассистенту (0 — без лимита). На публичном стенде защищают бюджет ключа.
    chat_user_hourly_limit: int = 0
    chat_daily_limit: int = 0
    # Модель, которая оценивает ответы в прогоне эталонных вопросов.
    llm_judge_model: str = "gpt-4o"


@lru_cache
def get_settings() -> Settings:
    return Settings()
