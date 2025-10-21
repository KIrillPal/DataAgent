import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Set

# Logfile for websocket debugging
LOGFILE = Path('/tmp/data_agent_ws.log')
logging.basicConfig(level=logging.INFO)

def log_msg(msg: str):
    """Log message to both console and logfile."""
    now = datetime.utcnow().isoformat()
    line = f"{now} {msg}\n"
    try:
        print(line, end='')
        with open(LOGFILE, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass

def extract_tool_signatures(calls) -> Set[str]:
    """Extract string signatures from tool call dicts for echo detection."""
    sigs = set()
    if not calls:
        return sigs
        
    def walk(val):
        if val is None:
            return
        if isinstance(val, str) and val:
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

    for call in calls:
        args = call.get('args') if isinstance(call, dict) else None
        walk(args)
        if isinstance(call, dict) and 'name' in call:
            sigs.add(str(call.get('name')))
            
    return sigs

def safe_json_loads(text: str) -> Dict[str, Any]:
    """Safely parse JSON with fallback."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"type": "echo", "payload": {"msg": text}}
    
def list_dir(path: str = ".", max_items: int = 100):
    """List directory contents."""
    base = Path(path).resolve()
    if not base.exists():
        return {"error": "path not found"}

    try:
        items = []
        for item_path in sorted(base.iterdir(), key=lambda x: (x.is_file(), x.name))[:max_items]:
            items.append({
                "name": item_path.name,
                "is_dir": item_path.is_dir(),
                "path": str(item_path),
            })
        return {"items": items}
    except Exception as e:
        return {"error": str(e)}