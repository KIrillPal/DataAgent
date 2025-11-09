if [ -f "data_agent/mcp/chartjs-mcp-server/dist/index.js" ]; \
    then echo "Chart.js MCP server already initialized. Skipping..."; \
    else cd data_agent/mcp/chartjs-mcp-server \
    && npm install \
    && npm run build; \
fi