FROM python:3.12-slim

ARG requirements_file=production.txt

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        libpq5 \
        postgresql-client \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app /var/log/ezl/etl /app/media /app/staticfiles
WORKDIR /app

COPY requirements/ /app/requirements/
RUN pip install --upgrade pip && pip install -r /app/requirements/${requirements_file}

COPY . /app

EXPOSE 8000 8002
CMD ["gunicorn", "ezl.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "600"]
