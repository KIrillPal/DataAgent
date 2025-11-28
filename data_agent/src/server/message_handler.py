from .connection_manager import ConnectionManager
from .data_agent_messenger import DataAgentMessenger
from typing import Dict, Any, Optional, List
import json

from .utils import list_dir

class MessageHandler:
    def __init__(self, connection_manager: ConnectionManager, data_agent_messenger: DataAgentMessenger):
        self.manager = connection_manager
        self.agent_messenger = data_agent_messenger

    ##########
    # Public #
    ##########

    async def route_message(self, client_id: str, message_type: str, payload: Dict[str, Any]):
        """Route message to appropriate handler based on type."""
        handler_map = {
            "list": lambda: self.handle_list(client_id, payload),
            "visualize": lambda: self.handle_visualize(client_id, payload),
            "query": lambda: self.handle_query(client_id, payload),
        }
        
        if handler := handler_map.get(message_type):
            await handler()
        else:
            await self.handle_echo(client_id, {"type": message_type, "payload": payload})

    async def convert_echo_to_query(self, payload: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        """Convert echo message to query for backwards compatibility."""
        if isinstance(payload, dict):
            msg_text = payload.get('msg') or payload.get('text')
        else:
            msg_text = str(payload)
            
        if not msg_text:
            msg_text = json.dumps(payload) if isinstance(payload, dict) else str(payload)
            
        return 'query', {'text': msg_text}
    
    ##################
    # Query handlers #
    ##################

    async def handle_list(self, client_id: str, payload: Dict[str, Any]):
        """Handle directory listing request."""
        path = payload.get("path", ".")
        res = await list_dir(path)
        await self.manager.send_json(client_id, {
            "type": "list_result", 
            "payload": res
        })

    async def handle_visualize(self, client_id: str, payload: Dict[str, Any]):
        """Handle visualization request."""
        items = payload.get("items", [])
        cards = [
            {
                "title": item.get('name'), 
                "subtitle": 'dir' if item.get('is_dir') else 'file'
            } 
            for item in items
        ]
        await self.manager.send_json(client_id, {
            "type": "visualize_result", 
            "payload": cards
        })

    async def handle_query(self, client_id: str, payload: Dict[str, Any]):
        """Handle agent query request."""
        query_text = payload.get('text', '')
        image_paths = payload.get('image_paths', [])
        
        try:
            agent = self.agent_messenger.get_agent()

            if agent is None:
                await self.__send_agent_error(client_id, "Agent not initialized")
            else:
                await self.__process_agent_response(client_id, agent, query_text, image_paths)
        except Exception as e:
            await self.__send_agent_error(client_id, str(e))


    async def handle_echo(self, client_id: str, data: Dict[str, Any]):
        """Handle echo message."""
        await self.manager.send_json(client_id, {"type": "echo", "payload": data})

    ###########
    # Private #
    ###########

    async def __process_agent_response(self, client_id: str, agent, query: str, image_paths: List[str] = []):
        """Process agent response and send appropriate messages."""
        messages = await agent.run(query, thread_id=client_id, verbose=True, image_paths=image_paths)
        results = []
        first_piece = True

        for message in messages[1:]:  # Skip first message to avoid echoing user's query back
            if tool_calls := self.__extract_tool_calls(message):
                await self.manager.send_json(client_id, {"type": "tool_calls", "payload": tool_calls})
                continue

            if content := self.__extract_content(message, message_type='AIMessage'):
                    send_text = content if first_piece else f" {content}"
                    first_piece = False
                    results.append({'content': send_text})

        await self.manager.send_json(client_id, {
            "type": "agent_result", 
            "payload": results
        })

    async def __send_agent_error(self, client_id: str, error: str):
        """Send agent error to client."""
        err_msg = {
            "type": "agent_error", 
            "payload": {
                "error": error,
                #"details": self.agent_messenger.get_init_error()
            }
        }
        await self.manager.send_json(client_id, err_msg)
    
    def __extract_tool_calls(self, message) -> Optional[list]:
        """Extract tool calls from message."""
        if hasattr(message, 'tool_calls'):
            return message.tool_calls
        elif isinstance(message, dict):
            return message.get('tool_calls')
        return None

    def __extract_content(self, message, message_type=None) -> Optional[str]:
        """Extract content from message."""
        if message_type and message.__class__.__name__ != message_type:
            return None
        if hasattr(message, 'content'):
            return message.content
        elif isinstance(message, dict):
            return message.get('content')
        return None