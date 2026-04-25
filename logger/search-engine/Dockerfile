FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV CC=gcc
ENV CXX=g++

WORKDIR /

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    curl \
    git \
    ca-certificates \
    build-essential \
    gcc \
    g++ \
    python3.9 \
    python3.9-dev \
    python3.9-distutils \
    python3.9-venv \
    openjdk-11-jdk \
    zlib1g-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.9

COPY requirements.txt requirements.txt

RUN python3.9 -m pip install --upgrade pip setuptools wheel && \
    python3.9 -m pip install -r requirements.txt && \
    python3.9 -m pip install --upgrade git+https://github.com/terrierteam/pyterrier_t5.git

COPY . .

CMD ["python3.9", "app.py"]