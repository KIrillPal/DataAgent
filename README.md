# DataAgent

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Poetry](https://img.shields.io/badge/poetry-managed-brightgreen.svg)](https://python-poetry.org/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](LICENSE.txt)

Beautiful, interactive agent for exploring and visualizing files and data in a repository. The agent can answer questions about the filesystem, produce charts and render them in a small web UI, and call read-only tools to inspect files.

---

## Features

- FastAPI-based web UI for interactive conversations with an agent.
- Agent capable of returning HTML snippets (charts, tables), which are sanitized and rendered client-side.
- Extensible toolset: read files, list directories, and produce visualizations.
- Hydra configuration system (configs are in `./configs`), allowing different model and agent configs.

---

## Examples

- Query: "Describe the data folder. What information do they have?"

![Demo](examples/demo.gif)

The question is about the tables from 'data' folder in the demo filesystem. It describes the content and draws some visuals.

- Query: "Draw a piechart on the number of files with each extension"

![Chart example 1](examples/chart1.png)

The entire dialogue with the charts are stored in its memory, so you can ask about the chart, as example: "What are the files with no extension?".
Or you can change the type of diagram.

![Chart example 2](examples/chart2.png)

- Query: "Describe briefly the structure of this repository. Visualize it as a graph"

![Filesystem example](examples/fs-example.png)

---

## Quick access

- Homepage: `http://localhost:8080` (default when running locally)
- Entry point: run `python -m data_agent` (the project is Poetry-managed)
- Provider's API key is stored to `.env` or inside the environment. Default provider is OpenRouter, env var: `OPENROUTER_API_KEY` (defined in `./configs`). 

---

## Usage

There are two recommended ways to run the project: Docker (recommended for reproducible runs) and Manual (developer-friendly, local environment).

### 1) Docker (recommended)

1. Clone this repository
    ```
    git clone --recurse-submodules https://github.com/KIrillPal/DataAgent.git
    cd DataAgent
    ```

2. Put OPENROUTER_API_KEY into .env

   ```sh
   echo OPENROUTER_API_KEY=sk-proj-... > .env
   ```

3. Build and run with Docker Compose (modern CLI):

   ```sh
   docker compose up --build
   ```

   The app will be available at `http://localhost:8080` by default (see `configs/app/default.yaml`).

Notes:

- The `./configs` folder is mounted into the container so you can edit configs on the host and the container will pick them up.
- Make sure the env var used by your selected model config is present in `.env` (e.g., `OPENROUTER_API_KEY`).

### 2) Manual

0. This repo uses Poetry for dependency management. Ensure you have Poetry installed.
   ```sh
   pip install --upgrade pip && pip install poetry
   ```

1. Create a virtual environment and install dependencies via Poetry:

   ```sh
   git clone --recurse-submodules https://github.com/KIrillPal/DataAgent.git
   cd DataAgent
   poetry install
   ```

2. Put OPENROUTER_API_KEY into .env

   ```sh
   echo OPENROUTER_API_KEY=sk-proj-... > .env
   ```

3. Run the app (Hydra will load configs from `./configs`):
    
   ```sh
   # default config runs the server (configs/default.yaml)
   python -m data_agent
   ```

   You can specify the config path using hydra arguments:

   ```sh
   python3 -m data_agent --config-dir=./configs --config-name=default
   ```

Environment variables

- Place API keys in the environment or in a `.env` file loaded by the app. The model config `configs/model/gpt-5.yaml` uses `api_env_var: OPENROUTER_API_KEY` (see `configs/model/gpt-5.yaml`).

---

## Configuration

Configs are managed via Hydra and live in `./configs`. The default configuration chain is defined in `configs/default.yaml` and selects a model (by default `gpt-5.yaml`), an agent config and app settings.

Common config paths:

- `configs/model/*.yaml` — model-specific settings and `api_env_var` key names.
- `configs/agent/*.yaml` — agent settings: prompt, limitations.
- `configs/app/*.yaml` — server configuration: host/port, etc.

To change config at runtime you can pass Hydra overrides. Example (run server with a different port):

```sh
python -m data_agent app.port=9000
```

---

## File structure

Top-level project layout:

```
./
├─ 📁 configs/                    # Hydra configuration tree (models, app, agent)
├─ 📁 data_agent/                 # Package source
│  ├─ 📁 src/
│  │  ├─ 📁 server/               # FastAPI app, websocket and message handler
│  │  ├─ 📄 data_agent.py         # Agent implementation and tools
│  │  └─ 📄 cli.py                # Hydra-based CLI and uvicorn launcher
│  ├─ 📁 mcp/                     # MCP Servers for the agent
│  ├─ 📁 static/                  # Static files for the web interface.
├─ 📄 pyproject.toml              # Poetry-managed project file
├─ 📄 poetry.lock                 # Locked dependencies
├─ 📄 Dockerfile                  # Docker file 
├─ 📄 docker-compose.yml          # Compose file (v2.4)
└─ 📄 README.md                   # This document
```

The important runtime entrypoint is `python -m data_agent` which dispatches to the Hydra CLI in `data_agent/src/cli.py`. By default that CLI will start the FastAPI server (see `configs/app/default.yaml`).

---

## Contributing

Contributions welcome. Please open issues or PRs. If adding features that change public behavior, add small tests and update the README with new usage examples.

---

## License

This project uses an MIT-style license (see `LICENSE.txt`).
