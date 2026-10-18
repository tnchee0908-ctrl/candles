import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import DomainError, RateLimited
from app.models import LoginFailure, User

PBKDF2_ITERATIONS = 200_000
log = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


# Значения-заглушки из примеров конфигурации: подписывать ими токены нельзя — их знает любой,
# кто видел репозиторий, и может выпустить себе токен руководителя.
WEAK_SECRETS = {"", "change-me-in-production", "dev-secret-change-me", "secret", "changeme"}
_generated_secret: str | None = None


def jwt_secret() -> str:
    global _generated_secret
    configured = get_settings().jwt_secret
    if configured not in WEAK_SECRETS and len(configured) >= 16:
        return configured
    if _generated_secret is None:
        _generated_secret = secrets.token_urlsafe(48)
        log.warning(
            "JWT_SECRET не задан или слабый — используется случайный секрет до перезапуска "
            "(после перезапуска нужно будет войти заново). Задайте JWT_SECRET в .env."
        )
    return _generated_secret


def create_token(user: User) -> str:
    settings = get_settings()
    payload = {"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(hours=settings.jwt_ttl_hours)}
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


async def authenticate(session: AsyncSession, username: str, password: str, ip: str = "unknown") -> User:
    """Вход с ограничением перебора: после N неудач подряд с одного адреса для логина — пауза.

    Считаем по паре «логин + адрес», а не по логину целиком: иначе любой мог бы заблокировать
    вход демо-пользователю, набрав пять неверных паролей.
    """
    settings = get_settings()
    login = username.strip().lower()[:64]
    ip = (ip or "unknown")[:64]
    since = datetime.now(UTC) - timedelta(minutes=settings.login_window_minutes)
    pair = await session.scalar(
        select(func.count())
        .select_from(LoginFailure)
        .where(LoginFailure.username == login, LoginFailure.ip == ip, LoginFailure.at >= since)
    )
    per_ip = await session.scalar(
        select(func.count()).select_from(LoginFailure).where(LoginFailure.ip == ip, LoginFailure.at >= since)
    )
    if (pair or 0) >= settings.login_max_failures or (per_ip or 0) >= settings.login_max_failures_per_ip:
        raise RateLimited(
            f"Слишком много неудачных попыток входа. Подождите {settings.login_window_minutes} минут "
            "и попробуйте снова."
        )
    user = await session.scalar(select(User).where(User.username == login))
    if user is None or not verify_password(password, user.password_hash):
        session.add(LoginFailure(username=login, ip=ip))
        await session.commit()
        raise DomainError("Неверный логин или пароль.")
    await session.execute(delete(LoginFailure).where(LoginFailure.username == login, LoginFailure.ip == ip))
    await session.commit()
    return user
