FROM python:3.11-slim

RUN apt-get -qq update && apt-get install -y --no-install-recommends g++ curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x ./loadgen.sh

ENTRYPOINT ./loadgen.sh
