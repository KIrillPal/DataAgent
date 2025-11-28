import json
from pathlib import Path
from typing import Dict, Any
import tempfile
import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
import io

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

# Config storage (set by cli.py when initializing the server)
_app_config = None

def set_app_config(cfg):
    """Set the app configuration from Hydra config."""
    global _app_config
    _app_config = cfg

def get_app_config():
    """Get the app configuration."""
    global _app_config
    return _app_config or {}

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

@app.get("/api/config/image-limits")
async def get_image_limits():
    """Get image file size limits from config."""
    cfg = get_app_config()
    image_config = cfg.get('image', {})
    return JSONResponse(
        status_code=200,
        content={
            "min_file_size": image_config.get('min_file_size', 1024),
            "max_file_size": image_config.get('max_file_size', 20 * 1024 * 1024)
        }
    )

@app.post('/api/upload_image')
async def upload_image(file: UploadFile = File(...)):
    """Upload an image file to temporary storage on the server."""
    try:
        # Get config limits
        cfg = get_app_config()
        image_config = cfg.get('image', {})
        min_size = image_config.get('min_file_size', 1024)  # 1 KB default
        max_size = image_config.get('max_file_size', 20 * 1024 * 1024)  # 20 MB default
        
        # Validate file is an image
        if not file.content_type or not file.content_type.startswith('image/'):
            return JSONResponse(
                status_code=400,
                content={"error": "File must be an image"}
            )
        
        # Read and validate image
        contents = await file.read()
        if not contents:
            return JSONResponse(
                status_code=400,
                content={"error": "Empty file"}
            )
        
        # Check file size
        file_size = len(contents)
        if file_size < min_size:
            return JSONResponse(
                status_code=400,
                content={"error": f"File too small (minimum {min_size} bytes)"}
            )
        if file_size > max_size:
            return JSONResponse(
                status_code=400,
                content={"error": f"File too large (maximum {max_size} bytes)"}
            )
        
        # Verify it's a valid image by trying to open it
        try:
            img = Image.open(io.BytesIO(contents))
            # Ensure it can be opened
            img.verify()
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid or corrupted image: {str(e)}"}
            )
        
        # Create temporary directory if it doesn't exist
        temp_dir = Path(tempfile.gettempdir()) / "dataagent_images"
        temp_dir.mkdir(exist_ok=True)
        
        # Generate unique filename
        file_ext = Path(file.filename).suffix or '.jpg'
        unique_filename = f"{uuid4()}{file_ext}"
        file_path = temp_dir / unique_filename
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(contents)
        
        log_msg(f"Image uploaded: {file_path}")
        
        return JSONResponse(
            status_code=200,
            content={"path": str(file_path)}
        )
        
    except Exception as e:
        log_msg(f"Image upload error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Server error: {str(e)}"}
        )

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