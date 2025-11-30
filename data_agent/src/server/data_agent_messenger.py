import traceback
from pathlib import Path
from typing import Optional, Dict

from data_agent.src.vllm_server import VLLMServer, VLLM_PROVIDER
from data_agent.src.data_agent import DataAgent
from .utils import log_msg


class DataAgentMessenger:
    def __init__(self, config : Optional[Dict] = None):
        if config is None:
            self.agent = None
        else:
            self.initialize_vllm(config)
            self.initialize_agent(config)

    def initialize_vllm(self, config : Dict, start : bool = True):
        """Initialize vLLM inference server."""
        self.vllm = None
        try:
            if config.model.provider != VLLM_PROVIDER:
                return None

            
            server_args = config.model.vllm.server_args
            server_args.update(config.model.vllm.get('parameters', {}))

            self.vllm = VLLMServer(
                model_name=config.model.model,
                host=config.model.vllm.host,
                port=config.model.vllm.port,
                tool_call_parser=config.model.vllm.tool_call_parser,
                server_args=server_args
            )
            if start:
                self.vllm.start_server(
                    wait_for_ready=True,
                    timeout=config.model.vllm.timeout
                )
            return self.vllm

        except Exception as e:
            tb = traceback.format_exc()
            log_msg(f"DataAgent init failed: {e}\n{tb}")
            self.agent = None
            return False

    def initialize_agent(self, config : Dict) -> bool:
        """Initialize DataAgent with configuration."""
        try:
            self.agent = DataAgent(config)
            return True

        except Exception as e:
            tb = traceback.format_exc()
            log_msg(f"DataAgent init failed: {e}\n{tb}")
            self.agent = None
            return False

    def get_agent(self):
        """Get agent instance, initializing if necessary."""
        return self.agent

    def get_init_error(self) -> Optional[str]:
        """Get initialization error from logfile."""
        try:
            with open('/tmp/data_agent_ws.log', 'r', encoding='utf-8') as f:
                return ''.join(f.readlines()[-30:])
        except Exception:
            return None
        
    def __del__(self):
        if self.vllm:
            assert self.vllm.stop_server()