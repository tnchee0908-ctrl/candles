FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Сначала только зависимости — слой кэшируется, пока не меняется pyproject.toml.
COPY pyproject.toml ./
RUN python -c "import tomllib; p = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
print('\n'.join(p['dependencies'] + p['optional-dependencies']['dev']))" > /tmp/requirements.txt \
 && pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .
RUN chmod +x start.sh

EXPOSE 8000
CMD ["./start.sh"]
