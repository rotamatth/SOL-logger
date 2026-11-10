FROM python:3.14.4-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock requirements.lock
# Wheels only, so no package runs its own setup script while installing, and every file must
# match a sha256 hash listed in requirements.lock (tools/hash_requirements_lock.py writes them).
RUN python -m pip install --only-binary :all: --require-hashes -r requirements.lock && python -m pip check

# Only what the app needs at run time: no tests, other requirement files or local secrets.
# tests/test_container_image.py fails when a file or folder is neither listed here nor
# deliberately left out.
COPY forms.py search_app.py search_backend.py student_progress.py student_recap.py study_progress.py ./
COPY data/ data/
COPY research_dashboard/ research_dashboard/
COPY static/ static/
COPY templates/ templates/
COPY tools/ tools/

ARG SOL_GIT_COMMIT=unknown
ARG SOL_APP_VERSION=v2
ENV SOL_GIT_COMMIT=${SOL_GIT_COMMIT}
ENV SOL_APP_VERSION=${SOL_APP_VERSION}

EXPOSE 7001

CMD ["gunicorn", "-w", "2", "--threads", "4", "--keep-alive", "75", "--graceful-timeout", "2", "-b", "0.0.0.0:7001", "search_app:app"]
