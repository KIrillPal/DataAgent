DataAgent - Local GUI Server

This adds a minimal FastAPI server and a static frontend to the existing DataAgent project.

Features
- FastAPI server serving static SPA at `/`
- WebSocket per-client session at `/ws/{client_id}`
- API endpoint `/api/list_dir` to list files
- Simple visualization tool that turns lists into UI cards

Run (development)

1. Create a virtual environment and install dependencies (or use Poetry):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # or `poetry install` if using poetry
```

Troubleshooting
- If you see "ModuleNotFoundError" for hydra/fastapi, ensure your virtualenv is activated and `pip install -r requirements.txt` completed without errors.


2. Run via the package entrypoint (Hydra controls settings):

```bash
python -m data_agent
```

Hydra configuration
- Default app config is in `configs/app/default.yaml`.
- To disable the server and run CLI REPL: `python -m data_agent app.run_server=False`
- To change host/port: `python -m data_agent app.host=0.0.0.0 app.port=9000`

Quick test

Open: http://127.0.0.1:8080/
