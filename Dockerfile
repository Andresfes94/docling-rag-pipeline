# === Build stage ===
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-core.txt .
RUN pip install --no-cache-dir --no-deps -r requirements-core.txt && \
    pip install --no-cache-dir -r requirements-core.txt  # second pass resolves deps

ARG INCLUDE_EXTRAS=false
COPY requirements-optional.txt .
RUN if [ "$INCLUDE_EXTRAS" = "true" ]; then \
        pip install --no-cache-dir -r requirements-optional.txt; \
    fi

COPY pyproject.toml .
COPY src/ src/
COPY profiles.yaml .
RUN pip install --no-cache-dir .

# === Production stage ===
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/src /app/src
COPY --from=builder /app/profiles.yaml .

RUN mkdir -p data/output data/chroma

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
