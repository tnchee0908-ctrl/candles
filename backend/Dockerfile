# runtime — рабочий образ (API, воркер, моки): только зависимости для работы и код приложения.
# test    — runtime + pytest/ruff + tests/: используется только сервисом tests (docker compose run --rm tests).

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Сначала только зависимости — слой кэшируется, пока не меняется pyproject.toml.
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" \
    > /tmp/requirements.txt \
 && pip install --no-cache-dir -r /tmp/requirements.txt

COPY alembic.ini start.sh ./
COPY alembic ./alembic
COPY app ./app
COPY mocks ./mocks
COPY eval ./eval
RUN chmod +x start.sh

EXPOSE 8000
CMD ["./start.sh"]


FROM runtime AS test

RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['optional-dependencies']['dev']))" \
    > /tmp/requirements-dev.txt \
 && pip install --no-cache-dir -r /tmp/requirements-dev.txt
COPY tests ./tests
CMD ["sh", "-c", "ruff check . && ruff format --check . && pytest -q"]
