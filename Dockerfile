FROM node:20-slim

WORKDIR /app

# Install python/pip
RUN apt-get update && \
    apt-get install -y python3-pip python3.11-venv

# Python dependencies installation
RUN python3 -m venv ~/venv \
  && . ~/venv/bin/activate \
  && pip install --upgrade pip && pip install poetry

# Project installation
COPY ./ pyproject.toml poetry.lock* /app
RUN . ~/venv/bin/activate \
  && python -m poetry install --no-interaction --no-ansi

EXPOSE 8080

# Run the server
CMD bash ./data_agent/mcp/scripts/chatjs-install.sh \
  && . ~/venv/bin/activate && python3 -m data_agent