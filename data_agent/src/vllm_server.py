import subprocess
import time
import requests
import threading
from typing import Optional, Dict, Any
import os
import signal

VLLM_PROVIDER = 'vllm'

class VLLMServer:
    def __init__(self, 
                 model_name: str = "HuggingFaceTB/SmolVLM-Instruct",
                 host: str = "localhost",
                 port: int = 8000,
                 server_args: Optional[Dict[str, Any]] = None):
        self.model_name = model_name
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}/v1"
        self.process = None
        self.is_running = False
        
        self.server_args = server_args or {
            "trust_remote_code": True,
            "served_model_name": "smolvlm",
            "max_model_len": 2048,
            "tensor_parallel_size": 1
        }
    
    def start_server(self, wait_for_ready: bool = True, timeout: int = 120) -> bool:
        """vLLM server start"""
        if self.is_running:
            print(f"Server is already running on {self.base_url}.")
            return True
        
        try:
            cmd = [
                "vllm", "serve", self.model_name,
                "--host", self.host,
                "--port", str(self.port),
                "--enable-auto-tool-choice", 
                "--tool-call-parser", "pythonic",
            ]
            
            for key, value in self.server_args.items():
                if isinstance(value, bool):
                    if value:
                        cmd.append(f"--{key}")
                else:
                    cmd.extend([f"--{key}", str(value)])
            
            print(f"Starting server via shell: {' '.join(cmd)}")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            def echo_pipe(pipe):
                for line in pipe:
                    print(f"[vLLM Server] {line.strip()}")
            
            threading.Thread(target=echo_pipe, kwargs={'pipe': self.process.stdout}, daemon=True).start()
            threading.Thread(target=echo_pipe, kwargs={'pipe': self.process.stderr}, daemon=True).start()
            
            if wait_for_ready:
                if self._wait_for_server_ready(timeout):
                    self.is_running = True
                    print("Server is successfully started!")
                    return True
                else:
                    print("Server waiting timeout exceeded. Aborting!")
                    self.stop_server()
                    return False
            else:
                self.is_running = True
                return True
                
        except Exception as e:
            print(f"Error while vLLM server starting: {e}")
            return False
    
    def _wait_for_server_ready(self, timeout: int = 120) -> bool:
        """Waiting for server is ready"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/models", timeout=5)
                if response.status_code == 200: # ok code 200
                    return True
            except requests.exceptions.RequestException:
                pass
            
            time.sleep(2)
        
        return False
    
    def stop_server(self) -> bool:
        """Stop the server"""
        if self.process:
            try:
                self.process.terminate()
                
                try:
                    self.process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                
                self.is_running = False
                self.process = None
                print("Server is stopped!")
                return True
                
            except Exception as e:
                print(f"Error while vLLM server stopping: {e}")
                return False
        return True
    
    def check_health(self) -> bool:
        """Server's healthcheck"""
        try:
            response = requests.get(f"{self.base_url}/models", timeout=10)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def __enter__(self):
        self.start_server()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_server()

    def __del__(self):
        self.stop_server()