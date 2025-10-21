import traceback
from pathlib import Path
from typing import Optional, Dict

from .utils import log_msg
from data_agent.src.data_agent import DataAgent


class DataAgentMessenger:
    def __init__(self, config : Optional[Dict] = None):
        if config is None:
            self.agent = None
        else:
            self.initialize_agent(config)

    def initialize_agent(self, config : Dict) -> bool:
        """Initialize DataAgent with configuration."""
        try:
            print(config)
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