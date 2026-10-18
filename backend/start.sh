#!/bin/sh
set -e
alembic upgrade head
python -m app.seed
# Стандартный access-лог uvicorn пишет адрес с параметрами (?supplier=…) — в них бывают ПДн.
# Вместо него — свой журнал запросов без query string (app/web.py, AccessLogMiddleware).
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log
