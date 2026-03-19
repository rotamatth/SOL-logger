FROM ubuntu:20.04

COPY requirements.txt requirements.txt

RUN apt-get update && \
    apt-get install -y openjdk-11-jdk && \
    apt-get install -y python3 python3-pip python3-dev && \
    apt-get install -y build-essential && \
    apt-get install -y libpcre3 libpcre3-dev && \
    apt-get install -y libxml2-dev libxslt1-dev zlib1g-dev && \
    apt-get install -y zip unzip && \
    python3 -m pip install --upgrade pip setuptools wheel && \
    python3 -m pip install -r requirements.txt
    # mkdir -p /root/.ir_datasets/downloads 

COPY . .

# RUN unzip datasets/argsme.zip -d /root/.ir_datasets/

EXPOSE 7002

ENTRYPOINT python3 app.py