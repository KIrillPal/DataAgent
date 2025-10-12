from typing import Dict, List
import os

try:
    from langchain.tools import BaseTool
except Exception:
    BaseTool = None


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

        if name == 'visualize':
            # lightweight visualize tool: returns JSON with __visualize__ key
            import json
            if BaseTool is not None:
                # define a proper BaseTool subclass with annotated fields to satisfy pydantic v2
                class VisualizeTool(BaseTool):
                    name: str = "visualize"
                    description: str = (
                        "Create a visualization payload from a list or comma-separated string. "
                        "Returns JSON with __visualize__ key."
                    )

                    def _run(self, query: str) -> str:
                        items = []
                        try:
                            parsed = json.loads(query)
                            if isinstance(parsed, list):
                                for p in parsed:
                                    items.append({"title": str(p), "subtitle": "unknown"})
                        except Exception:
                            for part in [p.strip() for p in query.replace(',', '\n').splitlines() if p.strip()]:
                                items.append({"title": part, "subtitle": "unknown"})
                        return json.dumps({"__visualize__": items})

                    async def _arun(self, query: str) -> str:  # pragma: no cover - optional async support
                        return self._run(query)

                tools.append(VisualizeTool())
            else:
                def visualize_tool(payload: str) -> str:
                    items = []
                    try:
                        parsed = json.loads(payload)
                        if isinstance(parsed, list):
                            for p in parsed:
                                items.append({"title": str(p), "subtitle": "unknown"})
                    except Exception:
                        for part in [p.strip() for p in payload.replace(',', '\n').splitlines() if p.strip()]:
                            items.append({"title": part, "subtitle": "unknown"})
                    return json.dumps({"__visualize__": items})

                tools.append(visualize_tool)

    # no global visualize tool adds here; tools are appended conditionally above based on config

    return tools