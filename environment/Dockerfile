FROM python:3.13-slim-bookworm

WORKDIR /app

RUN pip install --no-cache-dir \
    numpy==2.2.3 \
    pandas==2.2.3 \
    scipy==1.15.1 \
    && rm -rf /root/.cache/pip

RUN mkdir -p /app/data /app/output

COPY data/ /app/data/
