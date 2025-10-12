from typing import Any, Dict, Optional
import os
from langchain.memory import ConversationBufferMemory as MemBuffer
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent

from .tools import init as init_tools


class DataAgent:

    def __init__(self, config):
        self.config = config
        self.model  = self.init_model(config['model'])
        self.agent  = self.init_agent(config['agent'])
        self.memory = self.init_memory(config['agent'].get('memory', None))

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
        tool_names = agent_config.get('tools', {})
        self.tools = init_tools(tool_names)
        self.system_prompt = agent_config.get('prompt', '')

        agent = create_react_agent(
            model=self.model,
            tools=self.tools, 
            prompt=self.system_prompt,
            **agent_config.get('parameters', {})
        )
        return agent

    def init_memory(self, memory_config : Optional[Dict] = None) -> Optional[MemBuffer]:
        """
        Initialize the conversation memory.
        Args:
            memory_config: Configuration dictionary for memory. If None, no memory is used.
        Returns:
            Memory instance
        """
        if memory_config is None:
            return None
        
        memory = MemBuffer(
            **memory_config
        )
        return memory

    def run(self, prompt: str, verbose: bool = False) -> Any:
        """
        Run the agent with the given prompt and stream results.
        Args:
            prompt: Input text to process
            verbose: Whether to print detailed message sequence
        Returns:
            List of response messages
        """
        # Include memory in the input
        input_with_memory = {
            "messages": [("human", prompt)],
            "chat_history": self.memory.chat_memory.messages if self.memory else []
        }
        
        # Inference
        stream = self.agent.stream(input_with_memory)
        messages = []

        for response in stream:
            if "agent" not in response:
                continue
            if "messages" not in response['agent']:
                continue
            last_msg = response["agent"]["messages"][-1]
            messages.append(last_msg)
            if verbose:
                self._print_message("Streamed Message", last_msg)

        # Memorize the interaction
        if messages:
            self._update_memory_brief(prompt, messages)
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

    def _update_memory(self, messages: Any, only_answer: bool = True) -> None:
        """Update the conversation memory with new messages."""
        if self.memory is not None:
            for msg in messages:
                self.memory.chat_memory.add_message(msg)

    def _update_memory_brief(self, question: str, messages: Any) -> None:
        """Update the conversation memory only with the question and its answer."""
        if self.memory is not None:
            # Add the question to memory
            self.memory.chat_memory.add_user_message(question)
            # Add the last AI message to memory
            last_message_content = next((msg.content for msg in reversed(messages) if hasattr(msg, 'content')), None)
            if last_message_content:
                self.memory.chat_memory.add_ai_message(last_message_content)