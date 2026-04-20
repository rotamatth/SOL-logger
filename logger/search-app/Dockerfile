FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.9 and required tools
RUN apt-get update && \
    apt-get install -y software-properties-common curl && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y \
        python3.9 \
        python3.9-distutils \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Install pip specifically for Python 3.9
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.9

# ---- Diagnostic check (safe to keep or remove) ----
RUN python3.9 --version && \
    python3.9 -m pip --version && \
    which python3.9

COPY requirements.txt requirements.txt

# Install dependencies using Python 3.9 pip
RUN python3.9 -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7001

ENTRYPOINT ["python3.9", "search_app.py"]
