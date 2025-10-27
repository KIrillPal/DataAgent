import json
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .connection_manager import ConnectionManager
from .data_agent_messenger import DataAgentMessenger
from .message_handler import MessageHandler
from .utils import log_msg, safe_json_loads, list_dir

###########
# Globals #
###########

app = FastAPI()
manager = ConnectionManager()
data_agent_messenger = DataAgentMessenger()
message_handler = MessageHandler(manager, data_agent_messenger)

# Static files configuration
ROOT = Path(__file__).parent / "../.." / "static"
ROOT = ROOT.resolve()
app.mount("/static", StaticFiles(directory=str(ROOT)), name="static")

##############
# Server API #
##############

# HTTP Endpoints
@app.get("/")
async def index():
    index_file = ROOT / "index.html"
    return FileResponse(str(index_file))

@app.get("/api/list_dir")
async def list_dir_wrapper(path: str = ".", max_items: int = 100):
    return list_dir(path, max_items)

@app.post('/api/emit_tool_calls')
async def emit_tool_calls(request: Request):
    """Emit sample tool calls to connected clients."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    
    client_id = body.get('client_id') or request.query_params.get('client_id')
    sample_tool_calls = [
        {
            'name': 'read_file', 
            'args': {'file_path': 'data_agent/src/data_agent.py'}, 
            'id': 'call_test_1', 
            'type': 'tool_call'
        },
        {
            'name': 'list_directory', 
            'args': {'path': '.'}, 
            'id': 'call_test_2', 
            'type': 'tool_call'
        }
    ]

    payload = {"type": "tool_calls", "payload": sample_tool_calls}
    log_msg(f"EMIT_TOOL_CALLS requested for client={client_id}")

    sent_count = 0
    if client_id:
        try:
            await manager.send_json(client_id, payload)
            sent_count = 1
        except Exception:
            sent_count = 0
    else:
        # Broadcast to all clients
        for cid in list(manager.active_connections.keys()):
            try:
                await manager.send_json(cid, payload)
                sent_count += 1
            except Exception:
                continue

    return {"sent": sent_count, "payload": sample_tool_calls}

# WebSocket Endpoint
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    while True:
        raw_message = await websocket.receive_text()
        log_msg(f"INCOMING [{client_id}]: {raw_message}")
        
        data = safe_json_loads(raw_message)
        message_type = data.get("type")
        payload = data.get("payload", {})
        
        # Echo message
        if message_type == 'echo':
            message_type, payload = message_handler.convert_echo_to_query(payload)

        # Route message to appropriate handler
        await message_handler.route_message(client_id, message_type, payload)

@app.get("/static/<path:path>")
async def serve_static_file(path: str):
    """Serve static files from the static directory."""
    file_path = ROOT / path
    if file_path.exists():
        return FileResponse(str(file_path))
    raise HTTPException(status_code=404, detail="File not found")