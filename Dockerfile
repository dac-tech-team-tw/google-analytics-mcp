FROM python:3.12-slim

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy source first (needed for regular install)
COPY pyproject.toml .
COPY analytics_mcp/ analytics_mcp/

# Regular (non-editable) install so the package is embedded in the image
RUN pip install --no-cache-dir --retries 3 .

# Switch to non-root user
USER appuser

# Cloud Run injects PORT; default to 8000 locally
ENV PORT=8000

EXPOSE ${PORT}

CMD ["analytics-mcp-http"]
