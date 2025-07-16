import requests
from threading import Lock

class MCPClient:
    def __init__(self, server_url, auth=None):
        self.server_url = server_url
        self.auth = auth

    def call(self, method, params=None):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }
        headers = {"Content-Type": "application/json"}
        if self.auth:
            headers.update(self.auth)
        r = requests.post(self.server_url, json=payload, headers=headers, timeout=30)
        return r.json().get("result", r.json())

class MCPClientPool:
    def __init__(self):
        self._clients = {}
        self._lock = Lock()

    def get_client(self, name, url, auth=None):
        with self._lock:
            if name not in self._clients:
                self._clients[name] = MCPClient(url, auth)
            return self._clients[name]
