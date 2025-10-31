FROM node:18-slim

WORKDIR /app

# Install python/pip
RUN apt-get update
RUN apt-get install -y python3-pip python3.11-venv

# Copy application files
COPY . /app
COPY pyproject.toml /app
COPY poetry.lock* /app

# Dependencies installation
RUN python3 -m venv ~/venv
RUN . ~/venv/bin/activate \
  && pip install --upgrade pip && pip install poetry \
  && python -m poetry install --no-interaction --no-ansi

EXPOSE 8080

CMD . ~/venv/bin/activate && python3 -m data_agent