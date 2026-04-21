FROM ubuntu:20.04

# ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y software-properties-common curl && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y \
        python3.9 \
        python3.9-distutils \
        openjdk-11-jdk \
        git \
        zip \
        unzip \
        libpcre3 \
        libpcre3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install pip for Python 3.9
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.9

COPY requirements.txt requirements.txt
RUN python3.9 -m pip install -r requirements.txt && \
    python3.9 -m pip install --upgrade git+https://github.com/terrierteam/pyterrier_t5.git

COPY . .

EXPOSE 7002
ENTRYPOINT ["python3.9", "app.py"]