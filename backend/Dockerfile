FROM python:3.12-slim

WORKDIR /app

# git: the world library is a git repo (ADR 0008 D4/I5) — editor saves commit
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# Copy lockfile first for layer caching — reinstall only if deps change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
