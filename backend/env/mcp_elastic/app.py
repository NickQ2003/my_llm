from fastapi import FastAPI
from pydantic import BaseModel
import os, requests

app = FastAPI()

class MCPRequest(BaseModel):
    method: str
    params: dict = {}

def get_client_conf(client):
    client = client.upper()
    url = os.getenv(f"{client}_ELASTIC_API") or os.getenv("ELASTIC_API")
    key = os.getenv(f"{client}_ELASTIC_KEY") or os.getenv("ELASTIC_KEY")
    return url, key

@app.post("/")
def handle_mcp(request: MCPRequest):
    client = request.params.get("client", "DEFAULT")
    url, key = get_client_conf(client)
    if not url or not key:
        return {"jsonrpc": "2.0", "id": 1, "error": "API config missing for client"}

    if request.method == "analyze_logs":
        body = request.params.get("body", {})
        r = requests.post(
            f"{url}/search",
            headers={"Authorization": f"ApiKey {key}", "Content-Type": "application/json", "kbn-xsrf": "true"},
            json=body
        )
        return {"jsonrpc": "2.0", "id": 1, "result": r.json()}
    return {"jsonrpc": "2.0", "id": 1, "error": "Method not supported"}
