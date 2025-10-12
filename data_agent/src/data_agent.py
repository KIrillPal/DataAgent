from typing import Any, Dict, Optional, List
import os
import uuid
from langgraph.checkpoint.memory import MemorySaver
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, START, MessagesState
from langchain_core.messages import BaseMessage, HumanMessage

from .tools import init as init_tools


class DataAgent:

    def __init__(self, config):
        self.config = config
        self.model = self.init_model(config['model'])
        self.thread_id = str(uuid.uuid4())
        (self.agent, self.memory) = self.init_agent(config['agent'])

    def init_model(self, model_config: Dict) -> Any:
        """
        Initialize the chat model based on the configuration.
        
        Args:
            model_config: Configuration dictionary for the model
        Returns:
            Initialized chat model instance
        """
        provider = model_config['provider']
        model_name = model_config['model']

        API_KEY = os.getenv(model_config['api_env_var'])

        model = init_chat_model(
            model=model_name,
            model_provider=provider,
            api_key=API_KEY,
            **model_config.get('parameters', {})
        )
        return model

    def init_agent(self, agent_config: Dict) -> Any:
        """
        Initialize the agent with memory.

        Args:
            agent_config: Configuration dictionary for the agent
        Returns:
            Tuple of (agent instance, memory instance)
        """
        tool_names = agent_config.get('tools', {})
        self.tools = init_tools(tool_names)
        self.system_prompt = agent_config.get('prompt', '')

        memory = MemorySaver()
        
        agent = create_react_agent(
            model=self.model,
            tools=self.tools, 
            prompt=self.system_prompt,
            checkpointer=memory,
            **agent_config.get('parameters', {})
        )
        
        return agent, memory

    def run(self, prompt: str, verbose: bool = False, thread_id: Optional[str] = None) -> List[BaseMessage]:
        """
        Run the agent with the given prompt and stream results.
        
        Args:
            prompt: Input text to process
            verbose: Whether to print detailed message sequence
            thread_id: Optional thread ID for conversation tracking. 
                If not provided, uses default.
        Returns:
            List of response messages
        """
        # Use provided thread_id or default
        current_thread_id = thread_id or self.thread_id
        config = {"configurable": {"thread_id": current_thread_id}}
        
        input_message = HumanMessage(content=prompt)
        
        # Inference
        stream = self.agent.stream(
            {"messages": [input_message]}, 
            config, 
            stream_mode="values"
        )

        messages = []
        for event in stream:
            if "messages" in event:
                last_msg = event["messages"][-1]
                messages.append(last_msg)
                if verbose:
                    self._print_message("Streamed Message", last_msg)
        
        return messages

    def _print_message(self, header: str, msg: Any) -> None:
        """Print a single message with its details."""
        print(f"\n--- {header} ---")
        print(f"Type: {type(msg).__name__}")
        
        if hasattr(msg, 'content'):
            print(f"Content: {msg.content}")
        
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            print(f"Tool calls: {msg.tool_calls}")

    def get_chat_history(self, thread_id: Optional[str] = None) -> List[BaseMessage]:
        """
        Get conversation history for a thread.
        
        Args:
            thread_id: Optional thread ID (uses default if not provided)
        Returns:
            List of messages in the conversation
        """
        current_thread_id = thread_id or self.thread_id
        config = {"configurable": {"thread_id": current_thread_id}}
        
        # Get the current state to access history
        state = self.agent.get_state(config)
        return state.values.get("messages", []) if state else []

    def clear_memory(self, thread_id: Optional[str] = None) -> None:
        """
        Clear conversation memory for a thread.

        Args:
            thread_id: Optional thread ID (uses default if not provided)
        """
        current_thread_id = thread_id or self.thread_id
        config = {"configurable": {"thread_id": current_thread_id}}
        
        # Clear state by setting empty messages
        self.agent.update_state(config, {"messages": []})