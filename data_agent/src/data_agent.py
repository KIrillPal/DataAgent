from typing import Any, Dict
import os

from langchain.chat_models import init_chat_model
from langchain.agents import initialize_agent
from langchain.agents.agent_types import AgentType

from .tools import init as init_tools

class DataAgent:
    def __init__(self, config):
        self.config = config
        self.model = self.init_model(config['model'])
        self.agent = self.init_agent(config['agent'])

    def init_model(self, model_config : Dict):
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

    def init_agent(self, agent_config : Dict):
        # Initialize the agent with tools
        agent_type = agent_config.get('type', AgentType.ZERO_SHOT_REACT_DESCRIPTION)
        tool_names = agent_config.get('tools', {})

        # Init tools
        self.tools = init_tools(tool_names)
        self.system_prompt = agent_config.get('prompt', '')

        agent = initialize_agent(
            tools=self.tools, 
            llm=self.model,
            agent=agent_type,
            **agent_config.get('parameters', {})
        )
        return agent
    
    def run(self, prompt: str) -> Any:
        # Run the agent with the given prompt
        response = self.agent.invoke({"input": prompt})
        return response