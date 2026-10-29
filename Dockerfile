FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/appuser/.cache/huggingface

# libs de sistema exigidas pelo OpenCV/tableformer do Docling
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libxcb1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser assets/ ./assets/
USER appuser

# Converte um PDF mínimo no build para baixar/cachear os modelos do Docling.
ARG DOCLING_PREFETCH=1
RUN if [ "$DOCLING_PREFETCH" = "1" ]; then \
        python -c "from docling.document_converter import DocumentConverter; DocumentConverter().convert('assets/prefetch.pdf')"; \
    fi

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1"]
