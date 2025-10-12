from typing import Dict, List
import os


def init_filesystem_tools(tool_config: Dict):
    from langchain_community.agent_toolkits import FileManagementToolkit

    toolkit = FileManagementToolkit(
        root_dir=os.getcwd(),
        selected_tools=tool_config.get('permissions', [])
    )
    return toolkit.get_tools()


def init(config: Dict):
    tools = []

    for name, tool_config in config.items():
        if not tool_config['enabled']:
            continue
        if name == 'filesystem':
            tools.extend(init_filesystem_tools(tool_config))

    return tools