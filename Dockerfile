# Redline as a hosted demo: the same code and the same committed Relate store, read-only.
#   docker build -t redline . && docker run -p 7860:7860 redline     -> http://localhost:7860
# Hugging Face Spaces (Docker) serves port 7860 by default. Set REDLINE_ALLOWED_HOSTS to the public
# host name so MCP over HTTP answers there too, e.g. "you-redline.hf.space,you-redline.hf.space:*".
FROM python:3.12-slim

RUN useradd -m -u 1000 redline
WORKDIR /app
COPY pyproject.toml README.md ./
COPY redline redline
COPY ingest ingest
RUN pip install --no-cache-dir -e .
COPY web web
COPY data/redline-us data/redline-us
RUN chown -R redline /app
USER redline

ENV REDLINE_STORE=/app/data/redline-us PORT=7860 REDLINE_HOSTED=1
EXPOSE 7860
CMD ["sh", "-c", "redline serve --host 0.0.0.0 --port ${PORT}"]
