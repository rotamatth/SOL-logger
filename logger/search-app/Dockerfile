FROM python:3.14.4-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN python -m pip install -r requirements.txt

COPY . .

ARG SOL_GIT_COMMIT=unknown
ARG SOL_APP_VERSION=v2
ENV SOL_GIT_COMMIT=${SOL_GIT_COMMIT}
ENV SOL_APP_VERSION=${SOL_APP_VERSION}

EXPOSE 7001

CMD ["gunicorn", "-w", "2", "--threads", "4", "-b", "0.0.0.0:7001", "search_app:app"]
