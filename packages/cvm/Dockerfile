FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    CVM_DATA_DIR=/data \
    CVM_DB_PATH=/data/cvm.sqlite

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY cvm ./cvm
RUN uv pip install --system --no-cache .

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8347

CMD ["python", "-m", "cvm", "serve"]
