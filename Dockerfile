# DevHub Containerized Distribution
# Multi-stage build for minimal production image

FROM python:3.13-slim AS builder

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy source code
COPY src/ src/
COPY README.md ./

# Build the package
RUN uv build

# Production stage
FROM python:3.13-slim AS runtime

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install gh -y \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r devhub && useradd -r -g devhub -d /home/devhub -m devhub

# Copy built wheel from builder stage
COPY --from=builder /app/dist/*.whl /tmp/

# Install DevHub
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Switch to non-root user
USER devhub
WORKDIR /workspace

# Set up environment
ENV PATH="/home/devhub/.local/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD devhub --version || exit 1

# Default command
ENTRYPOINT ["devhub"]
CMD ["--help"]

# Metadata
LABEL org.opencontainers.image.title="DevHub" \
      org.opencontainers.image.description="CLI tool to bundle Jira tickets, GitHub PRs, diffs, and comments for code review" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.authors="hakimjonas" \
      org.opencontainers.image.url="https://github.com/hakimjonas/devhub" \
      org.opencontainers.image.source="https://github.com/hakimjonas/devhub" \
      org.opencontainers.image.licenses="MIT"