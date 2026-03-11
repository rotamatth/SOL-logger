FROM ubuntu:20.04

COPY requirements.txt requirements.txt

RUN apt-get update && \
    apt-get install -y python3 && \
    apt-get install -y python3-pip && \
    python3 -m pip install -r requirements.txt 
COPY . .

EXPOSE 7001

ENTRYPOINT python3 search_app.py