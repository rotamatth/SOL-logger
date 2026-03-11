FROM ubuntu:20.04

COPY requirements.txt requirements.txt

RUN apt-get update && \
    apt-get install openjdk-11-jdk -y && \
    apt-get install -y python3 && \
    apt-get install -y python3-pip && \
    apt-get install -y libpcre3 libpcre3-dev && \
    apt-get install zip unzip && \
    python3 -m pip install -r requirements.txt
    # mkdir -p /root/.ir_datasets/downloads 

COPY . .

# RUN unzip datasets/argsme.zip -d /root/.ir_datasets/

EXPOSE 7002

ENTRYPOINT python3 app.py