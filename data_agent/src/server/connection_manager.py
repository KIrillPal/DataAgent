import json
from typing import Dict, Any
from fastapi import WebSocket
from .utils import log_msg

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        await self._send_acknowledgment(client_id, websocket)

    async def _send_acknowledgment(self, client_id: str, websocket: WebSocket):
        """Send connection acknowledgment to client."""
        ack = {"type": "connected", "payload": {"client_id": client_id}}
        try:
            await websocket.send_json(ack)
            log_msg(f"OUTGOING [{client_id}]: {json.dumps(ack)}")
        except Exception:
            pass

    def disconnect(self, client_id: str):
        self.active_connections.pop(client_id, None)

    async def send_json(self, client_id: str, data: Any):
        """Send JSON data to specific client."""
        if ws := self.active_connections.get(client_id):
            await ws.send_json(data)
            log_msg(f"OUTGOING [{client_id}]: {json.dumps(data)}")