from http.client import responses
from typing import Any, Dict
import os
from urllib import response

from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent

from .tools import init as init_tools

class DataAgent:
    def __init__(self, config):
        self.config = config
        self.model = self.init_model(config['model'])
        self.agent = self.init_agent(config['agent'])

    def init_model(self, model_config : Dict) -> Any:
        """
        Initialize the chat model based on the configuration.
        Args:
            model_config: Configuration dictionary for the model
        Returns:
            Initialized chat model instance
        """
        # Load the API-based model
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

    def init_agent(self, agent_config : Dict) -> Any:
        """
        Initialize the agent with the specified tools and prompt.
        Args:
            agent_config: Configuration dictionary for the agent
        Returns:
            Initialized agent instance
        """
        # Initialize the agent with tools
        tool_names = agent_config.get('tools', {})

        # Init tools
        self.tools = init_tools(tool_names)
        self.system_prompt = agent_config.get('prompt', '')

        agent = create_react_agent(
            model=self.model,
            tools=self.tools, 
            prompt=self.system_prompt,
            **agent_config.get('parameters', {})
        )
        return agent

    def run(self, prompt: str, verbose: bool = False) -> Any:
        """Run the agent with the given prompt and stream results.

        Args:
            prompt: Input text to process
            verbose: Whether to print detailed message sequence
        
        Returns:
            List of response messages
        """
        stream = self.agent.stream({"messages": [("human", prompt)]})
        messages = []

        for response in stream:
            if "agent" not in response:
                continue
            if "messages" not in response['agent']:
                continue

            last_msg = response["agent"]["messages"][-1]
            self._print_message("Streamed Message", last_msg)
            messages.append(last_msg)

        # if verbose and messages:
        #     self._plot_message_sequence(messages[-1])

        return messages

    def _print_message(self, header: str, msg: Any) -> None:
        """Print a single message with its details."""
        print(f"\n--- {header} ---")
        print(f"Type: {type(msg).__name__}")
        
        if hasattr(msg, 'content'):
            print(f"Content: {msg.content}")
        
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            print(f"Tool calls: {msg.tool_calls}")

    def _plot_message_sequence(self, response: Any) -> None:
        """Plot the full sequence of messages in a response."""
        print("\nMessage sequence:")
        for i, msg in enumerate(response["messages"]):
            self._print_message(f"Message {i+1}", msg)