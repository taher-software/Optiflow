FROM python:3.13-slim AS optiflow_backend

# Unbuffered stdout/stderr so Cloud Run captures logs as they happen; no .pyc
# written into the image layers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first, in their own layer: rebuilding after a source-only change
# then reuses the cached install instead of re-downloading every package.
# Runtime requirements only — requirements-dev.txt (pytest, factory-boy, httpx)
# has no place in a production image, and `tests/` is not even shipped.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Documentation only; Cloud Run injects the real port through $PORT.
EXPOSE 8080

# `${PORT:-8080}` so the image also runs locally (`docker run -p 8080:8080`),
# where PORT is not set and an empty --port would abort the startup.
CMD ["sh", "-c", "uvicorn src.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
