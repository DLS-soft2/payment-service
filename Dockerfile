# Multi-stage build for the Payment Service.
#
# Stage 1 (builder): installs dependencies using Poetry
# Stage 2 (runtime): copies only what's needed to run
#
# This keeps the final image small — no Poetry, no build tools,
# just Python + the installed packages + our application code.

# --- Stage 1: Install dependencies ---
FROM python:3.12-slim AS builder

WORKDIR /build

# Install Poetry
RUN pip install poetry --no-cache-dir

# Copy only dependency files first (Docker layer caching optimization).
# If pyproject.toml hasn't changed, Docker reuses the cached layer
# and skips the slow `poetry install` step.
COPY pyproject.toml poetry.lock* ./

# Export to requirements.txt and install with pip
# (avoids needing Poetry in the runtime image)
RUN poetry export -f requirements.txt --without-hashes -o requirements.txt && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime image ---
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/

# Run the FastAPI server
# --host 0.0.0.0 makes it accessible from outside the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
