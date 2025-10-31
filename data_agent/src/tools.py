from typing import Dict, List
import asyncio
import json
import os


def init_filesystem_tools(tool_config: Dict):
    from langchain_community.agent_toolkits import FileManagementToolkit

    toolkit = FileManagementToolkit(
        root_dir=os.getcwd(),
        selected_tools=tool_config.get('permissions', [])
    )
    return toolkit.get_tools()


def init_mcp_tools(tool_config: Dict):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    with open(tool_config['path'], 'r') as f:
        mcp_config = json.load(f)
    
    mcp_client = MultiServerMCPClient(mcp_config)
    return asyncio.run(mcp_client.get_tools())


def init(config: Dict):
    tools = []

    for name, tool_config in config.items():
        if not tool_config.get('enabled', False):
            continue
        if name == 'filesystem':
            tools.extend(init_filesystem_tools(tool_config))

        if name == 'mcp':
            tools.extend(init_mcp_tools(tool_config))
    
    return tools