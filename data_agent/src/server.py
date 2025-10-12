import json
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
                        # If agent provides a stream method, stream partial outputs
                        if hasattr(agent, 'agent') and hasattr(agent.agent, 'stream'):
                            # create a generator and forward partial text events
                            cfg = {"configurable": {"thread_id": client_id}}
                            stream = agent.agent.stream({'messages': [{'role': 'user', 'content': q}]}, cfg, stream_mode='values')
                            for event in stream:
                                # event may contain 'messages' with partial content
                                if 'messages' in event:
                                    last = event['messages'][-1]
                                    if hasattr(last, 'content'):
                                        # Send partial content
                                        out = {"type": "agent_stream", "payload": {'content': last.content}}
                                        log_msg(f"OUTGOING [{client_id}]: {json.dumps(out)}")
                                        await manager.send_json(client_id, out)
                                        # Check if content contains a visualization payload
                                        try:
                                            parsed = json.loads(last.content)
                                            if isinstance(parsed, dict) and '__visualize__' in parsed:
                                                items = parsed['__visualize__']
                                                await manager.send_json(client_id, {"type": "visualize_result", "payload": items})
                                        except Exception:
                                            pass
                            # After stream ends, send end marker
                            endmsg = {"type": "agent_stream_end", "payload": {}}
                            log_msg(f"OUTGOING [{client_id}]: {json.dumps(endmsg)}")
                            await manager.send_json(client_id, endmsg)
                        else:
                            # fallback to non-streaming run() — pass thread_id so checkpointer works
                            messages = agent.run(q, thread_id=client_id)
                            results = []
                            for m in messages:
                                if hasattr(m, 'content'):
                                    results.append({'content': m.content})
                                    # detect visualization payloads in final content
                                    try:
                                        parsed = json.loads(m.content)
                                        if isinstance(parsed, dict) and '__visualize__' in parsed:
                                            items = parsed['__visualize__']
                                            # send visualization as a separate message
                                            vizmsg = {"type": "visualize_result", "payload": items}
                                            log_msg(f"OUTGOING [{client_id}]: {json.dumps(vizmsg)}")
                                            await manager.send_json(client_id, vizmsg)
                                    except Exception:
                                        pass
                            outmsg = {"type": "agent_result", "payload": results}
                            log_msg(f"OUTGOING [{client_id}]: {json.dumps(outmsg)}")
                            await manager.send_json(client_id, outmsg)
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
