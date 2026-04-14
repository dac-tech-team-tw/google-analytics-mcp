FROM python:3.12-slim

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Install dependencies first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir -e .

# Copy source
COPY analytics_mcp/ analytics_mcp/

# Switch to non-root user
USER appuser

# Cloud Run injects PORT; default to 8000 locally
ENV PORT=8000

EXPOSE ${PORT}

CMD ["sh", "-c", "analytics-mcp-http"]
