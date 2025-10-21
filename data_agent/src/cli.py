import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

import hydra
from omegaconf import DictConfig
from .data_agent import DataAgent
from . import server
import uvicorn

@hydra.main(config_path="../../configs", config_name="default", version_base=None)
def main(cfg: DictConfig) -> None:
    """
    CLI application that runs DataAgent to answer questions about the current working directory.
    
    Args:
        cfg: Hydra configuration
    """
    load_dotenv()  # Load environment variables to get API keys if present

    # If configured to run server, launch FastAPI app
    if cfg.app.get('run_server', False):
        host = cfg.app.get('host', '127.0.0.1')
        port = int(cfg.app.get('port', 8080))
        server.data_agent_messenger.initialize_agent(cfg)
        # serve static files and API
        uvicorn.run(server.app, host=host, port=port)
        return

    agent = DataAgent(cfg)
    verbose = cfg.agent.get('verbose', False)
    
    while True:
        try:
            # Get user input
            question = input("\nAsk a question about the current directory (or 'exit' to quit): ")
            
            if question.lower() in ['exit', 'quit']:
                print("Goodbye!")
                break
                
            prompt = f"""
            Current working directory: {os.getcwd()}
            Question: {question}
            """

            # Run the agent with the prompt
            messages = agent.run(prompt, verbose=verbose)

            if not verbose:
                for m in messages:
                    if hasattr(m, 'content'):
                        print(f"{m.content}")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break

if __name__ == "__main__":
    main()
