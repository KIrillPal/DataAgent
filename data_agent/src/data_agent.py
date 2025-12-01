import asyncio
import sys
from typing import Any, Dict, Optional, List, TextIO
import os
import uuid
import base64
from io import BytesIO
from PIL import Image
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langchain.chat_models import init_chat_model
from langchain_openai.chat_models.base import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, START, MessagesState
from langchain_core.messages import BaseMessage, HumanMessage
from transformers import AutoProcessor, AutoModelForImageTextToText, pipeline
from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline

from .vllm_server import VLLM_PROVIDER
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
        
        if provider == VLLM_PROVIDER:
            return self.init_vllm_model(model_config)
        elif provider == 'huggingface':
            return self.init_huggingface_model(model_config)
        else:
            return self.init_api_model(model_config)

    def init_api_model(self, model_config: Dict) -> Any:
        """
        Initialize the chat model based on the configuration with API key.
        
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
    
    def init_vllm_model(self, model_config: Dict) -> Any:
        """
        Initialize the chat model based on the configuration 
        with vLLM server running.
        
        Args:
            model_config: Configuration dictionary for the model
        Returns:
            Initialized chat model instance
        """
        model_name = model_config['model']
        host = model_config['vllm']['host']
        port = model_config['vllm']['port']
        base_url = f"http://{host}:{port}/v1"

        model = ChatOpenAI(
            model=model_name,
            base_url=base_url,
            api_key="foo",
            **model_config.get('parameters', {})
        )
        return model
    
    def init_huggingface_model(self, model_config: Dict) -> Any:
        """
        Initialize a Hugging Face model with ChatHuggingFace for multimodal inference.
        Correctly supports VLMs like Qwen2-VL.

        Args:
            model_config: Configuration dictionary for the model
        Returns:
            Initialized ChatHuggingFace instance
        """

        model_id = model_config['model']
        device = model_config.get('huggingface', {}).get('device_map', 'auto')

        if device == 'auto':
            app_config = self.config['app']
            if app_config and 'inference' in app_config and 'device' in app_config['inference']:
                device = app_config['inference']['device']
        if device == 'auto':
            device = 'cpu'

        # 1. Load the correct processor and model for the VLM
        processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            device_map=device,
            dtype="auto",
            trust_remote_code=True
        )

        pipe = pipeline(
            task="image-text-to-text",
            model=model,
            processor=processor,
            **model_config.get('pipeline_kwargs', {})
        )
        llm = HuggingFacePipeline(pipeline=pipe)
        chat_model = ChatHuggingFace(llm=llm)

        return chat_model

    def init_agent(self, agent_config: Dict) -> Any:
        """
        Initialize the agent with memory.

        Args:
            agent_config: Configuration dictionary for the agent
        Returns:
            Tuple of (agent instance, memory instance)
        """
        tool_names = agent_config.get('tools', {})
        app_config = self.config.get('app', {})
        self.tools = init_tools(tool_names, app_config)
        self.system_prompt = agent_config.get('prompt', '')
        self.recursion_limit = agent_config.get('recursion_limit', -1)

        memory = MemorySaver()
        
        agent = create_react_agent(
            model=self.model,
            tools=self.tools, 
            prompt=self.system_prompt,
            checkpointer=memory,
            **agent_config.get('parameters', {})
        )
        
        return agent, memory

    async def run(
            self, 
            prompt: str, 
            verbose: bool = False, 
            thread_id: Optional[str] = None,
            image_paths: List[Path | str] = []
        ) -> List[BaseMessage]:
        """
        Run the agent with optional image input.
        
        Args:
            prompt: Input text to process
            verbose: Whether to print detailed message sequence
            thread_id: Optional thread ID for conversation tracking
            image_paths: List with image files for multimodal processing
        Returns:
            List of response messages
        """
        # Use provided thread_id or default
        current_thread_id = thread_id or self.thread_id
        config = {
            "configurable": {"thread_id": current_thread_id}, 
            "recursion_limit": self.recursion_limit
        }
        
        input_message = self._create_human_message(prompt, image_paths)

        with open(f"outputs/{current_thread_id}.txt", "w") as f:
            print("Inference started...", flush=True, file=f)
            
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
                        self._print_message("Streamed Message", last_msg, file=f)
        
        # Check last message content and handle empty case
        if messages and not messages[-1].content:
            messages[-1].content = self.config['agent'].get('exceed_message', '')
        return messages

    def _print_message(self, header: str, msg: Any, file: TextIO = sys.stdout) -> None:
        """Print a single message with its details."""
        print(f"\n--- {header} ---", flush=True, file=file)
        print(f"Type: {type(msg).__name__}", flush=True, file=file)

        if hasattr(msg, 'content'):
            print(f"Content: {msg.content}", flush=True, file=file)

        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            print(f"Tool calls: {msg.tool_calls}", flush=True, file=file)

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
        self.agent.update_state(config, {"messages": []})

    def _image_to_base64(self, image_path: Path | str) -> str:
        """Convert image to base64 string"""
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
        
    def _create_human_message(self, prompt: str, image_paths: List[Path | str]):
        content = []

        for img_p in image_paths:
            base64_image = self._image_to_base64(img_p)
            content.append({
                "type": "text",
                "text": f"[Attached image path: {str(img_p)}]"
            })
            content.append({
                "type": "image_url",
                "image_url": { "url": f"data:image/jpeg;base64,{base64_image}" }
            })
        
        content.append({
            "type": "text", 
            "text": prompt
        })
        return HumanMessage(content=content)