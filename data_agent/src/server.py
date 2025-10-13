import json
import ast
import os
import traceback
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# logfile for websocket debugging
LOGFILE = Path('/tmp/data_agent_ws.log')
logging.basicConfig(level=logging.INFO)

def log_msg(msg: str):
    # print and append to logfile for persistent debugging
    now = datetime.utcnow().isoformat()
    line = f"{now} {msg}\n"
    try:
        print(line, end='')
    except Exception:
        pass
    try:
        with open(LOGFILE, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass


def _extract_tool_signatures(calls):
    """Return a set of string signatures extracted from a list of tool call dicts.

    Useful to heuristically detect textual echoes of tool outputs (filenames, query strings).
    """
    sigs = set()
    if not calls:
        return sigs
    def walk(val):
        if val is None:
            return
        if isinstance(val, str):
            if val:
                sigs.add(val)
        elif isinstance(val, (list, tuple, set)):
            for v in val:
                walk(v)
        elif isinstance(val, dict):
            for v in val.values():
                walk(v)
        else:
            try:
                s = str(val)
                if s:
                    sigs.add(s)
            except Exception:
                pass
    for c in calls:
        args = c.get('args') if isinstance(c, dict) else None
        walk(args)
        # also include name
        if isinstance(c, dict) and 'name' in c:
            sigs.add(str(c.get('name')))
    return sigs

# Try to import and initialize DataAgent lazily to avoid hard dependency failures
AGENT_INSTANCE = None

def init_data_agent(cfg=None):
    global AGENT_INSTANCE
    if AGENT_INSTANCE is not None:
        return AGENT_INSTANCE
    try:
        # Load .env from project root so API keys are available
        from dotenv import load_dotenv
        project_root = Path(__file__).resolve().parents[2]
        env_path = project_root / '.env'
        if env_path.exists():
            load_dotenv(str(env_path))

        # Import DataAgent and build from Hydra config if available
        from data_agent.src.data_agent import DataAgent
        from omegaconf import OmegaConf
        # Load Hydra config from repository configs
        cfg_dir = Path(__file__).resolve().parents[2] / 'configs'
        # Attempt to load sensible defaults (fall back to known names)
        try:
            model_cfg = OmegaConf.load(cfg_dir / 'model' / 'gpt-5-nano.yaml')
        except Exception:
            # pick first yaml in model/
            files = list((cfg_dir / 'model').glob('*.yaml'))
            model_cfg = OmegaConf.load(files[0]) if files else {}

        try:
            agent_cfg = OmegaConf.load(cfg_dir / 'agent' / 'react.yaml')
        except Exception:
            files = list((cfg_dir / 'agent').glob('*.yaml'))
            agent_cfg = OmegaConf.load(files[0]) if files else {}

        try:
            app_cfg = OmegaConf.load(cfg_dir / 'app' / 'default.yaml')
        except Exception:
            app_cfg = {}

        cfg_obj = {
            'model': OmegaConf.to_container(model_cfg, resolve=True) if model_cfg else {},
            'agent': OmegaConf.to_container(agent_cfg, resolve=True) if agent_cfg else {},
            'app': OmegaConf.to_container(app_cfg, resolve=True) if app_cfg else {},
        }

        AGENT_INSTANCE = DataAgent(cfg_obj)
        return AGENT_INSTANCE
    except Exception as e:
        # Log full traceback to help diagnose why DataAgent failed to initialize
        tb = traceback.format_exc()
        log_msg(f"DataAgent init failed: {e}\n{tb}")
        AGENT_INSTANCE = None
        return None



ROOT = Path(__file__).parent / ".." / "static"
ROOT = ROOT.resolve()

app.mount("/static", StaticFiles(directory=str(ROOT)), name="static")


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        # send a connection acknowledgment so clients know the handshake succeeded
        try:
            ack = {"type": "connected", "payload": {"client_id": client_id}}
            await websocket.send_json(ack)
            log_msg(f"OUTGOING [{client_id}]: {json.dumps(ack)}")
        except Exception:
            pass

    def disconnect(self, client_id: str):
        self.active_connections.pop(client_id, None)

    async def send_json(self, client_id: str, data: Any):
        ws = self.active_connections.get(client_id)
        if ws:
            await ws.send_json(data)


manager = ConnectionManager()


@app.get("/")
async def index():
    index_file = ROOT / "index.html"
    return FileResponse(str(index_file))


@app.get("/api/list_dir")
async def list_dir(path: str = ".", max_items: int = 100):
    base = Path(path).resolve()
    if not base.exists():
        return {"error": "path not found"}

    items = []
    try:
        for p in sorted(base.iterdir(), key=lambda x: (x.is_file(), x.name))[:max_items]:
            items.append({
                "name": p.name,
                "is_dir": p.is_dir(),
                "path": str(p),
            })
    except Exception as e:
        return {"error": str(e)}

    return {"items": items}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    try:
        agent = init_data_agent()
        while True:
            # receive raw text and log it for debugging (some clients may send text frames)
            raw = await websocket.receive_text()
            log_msg(f"INCOMING [{client_id}]: {raw}")
            try:
                data = json.loads(raw)
            except Exception:
                # try to recover by reading as JSON via receive_json
                try:
                    data = await websocket.receive_json()
                except Exception:
                    data = {"type": "echo", "payload": {"msg": raw}}
            # Simple protocol: {type: 'query'|'list'|'visualize'|'echo', payload: {...}}
            t = data.get("type")
            payload = data.get("payload", {})

            # Backwards compatibility: treat 'echo' as a user query carrying payload.msg
            if t == 'echo':
                # If payload contains a msg field, use that as the query text
                msg_text = None
                if isinstance(payload, dict):
                    msg_text = payload.get('msg') or payload.get('text')
                # Fallback to stringified payload
                if not msg_text:
                    try:
                        msg_text = json.dumps(payload)
                    except Exception:
                        msg_text = str(payload)
                t = 'query'
                payload = {'text': msg_text}

            if t == "list":
                path = payload.get("path", ".")
                res = await list_dir(path)
                await manager.send_json(client_id, {"type": "list_result", "payload": res})
            elif t == "visualize":
                # For now, just echo a stylized list card
                items = payload.get("items", [])
                cards = [{"title": it.get('name'), "subtitle": 'dir' if it.get('is_dir') else 'file'} for it in items]
                await manager.send_json(client_id, {"type": "visualize_result", "payload": cards})
            elif t == 'query':
                q = payload.get('text', '')
                # track whether we've sent the first piece for this query
                first_piece = True
                # If agent wasn't initialized at connect time, try again now (in case .env or config changed)
                if agent is None:
                    agent = init_data_agent()
                if agent is None:
                    # read last init failure from logfile if present
                    init_err = None
                    try:
                        with open(str(LOGFILE), 'r', encoding='utf-8') as f:
                            init_err = ''.join(f.readlines()[-30:])
                    except Exception:
                        init_err = None
                    err = {"type": "agent_error", "payload": {"error": "agent not initialized", "details": init_err}}
                    log_msg(f"OUTGOING [{client_id}]: {json.dumps(err)}")
                    await manager.send_json(client_id, err)
                else:
                    # Prefer streaming API if available
                    try:
                        messages = agent.run(q, thread_id=client_id, verbose=True)
                        for m in messages:
                            # Check for tool_calls attached to the message object first
                            tc = getattr(m, 'tool_calls', None) if hasattr(m, 'tool_calls') or hasattr(m, 'tool_calls') else None
                            if tc is None and isinstance(m, dict):
                                tc = m.get('tool_calls')
                            if tc:
                                log_msg(f"OUTGOING [{client_id}]: tool_calls payload detected (non-stream)")
                                await manager.send_json(client_id, {"type": "tool_calls", "payload": tc})
                                continue

                            content = getattr(m, 'content', None) if hasattr(m, 'content') else (m.get('content') if isinstance(m, dict) else None)
                            cls_name = m.__class__.__name__ if hasattr(m, '__class__') else None

                            if cls_name == 'AIMessage' and content is not None:
                                # prefix subsequent final pieces with newline
                                send_text = content if first_piece else ("\n" + content)
                                first_piece = False
                                outmsg = {"type": "agent_result", "payload": send_text}
                                log_msg(f"OUTGOING [{client_id}]: {json.dumps(outmsg)}")
                                await manager.send_json(client_id, outmsg)
                        await manager.send_json(client_id, {"type": "agent_done", "payload": {}})
                    except Exception as e:
                        err = {"type": "agent_error", "payload": {"error": str(e)}}
                        log_msg(f"OUTGOING [{client_id}]: {json.dumps(err)}")
                        await manager.send_json(client_id, err)
            else:
                # Echo
                out = {"type": "echo", "payload": data}
                log_msg(f"OUTGOING [{client_id}]: {json.dumps(out)}")
                await manager.send_json(client_id, out)

    except WebSocketDisconnect:
        manager.disconnect(client_id)


@app.post('/api/emit_tool_calls')
async def emit_tool_calls(request: Request):
    """Emit a sample tool_calls payload to a connected client or return it in the response.

    Sends to 'client_id' query param if provided, otherwise broadcasts to all connected clients.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    client_id = body.get('client_id') or request.query_params.get('client_id')

    sample = [
        {'name': 'read_file', 'args': {'file_path': 'data_agent/src/data_agent.py'}, 'id': 'call_test_1', 'type': 'tool_call'},
        {'name': 'list_directory', 'args': {'path': '.'}, 'id': 'call_test_2', 'type': 'tool_call'}
    ]

    payload = {"type": "tool_calls", "payload": sample}
    log_msg(f"EMIT_TOOL_CALLS requested for client={client_id}; broadcasting payload")

    sent = 0
    if client_id:
        try:
            await manager.send_json(client_id, payload)
            sent = 1
        except Exception:
            sent = 0
    else:
        # broadcast
        for cid, ws in list(manager.active_connections.items()):
            try:
                await manager.send_json(cid, payload)
                sent += 1
            except Exception:
                pass

    return {"sent": sent, "payload": sample}
