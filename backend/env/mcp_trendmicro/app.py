from fastapi import FastAPI
from pydantic import BaseModel
import os, requests

app = FastAPI()

class MCPRequest(BaseModel):
    method: str
    params: dict = {}

def get_client_conf(client):
    client = client.upper()
    url = os.getenv(f"{client}_TRENDMICRO_API") or os.getenv("TRENDMICRO_API")
    key = os.getenv(f"{client}_TRENDMICRO_KEY") or os.getenv("TRENDMICRO_KEY")
    return url, key

@app.post("/")
def handle_mcp(request: MCPRequest):
    client = request.params.get("client", "DEFAULT")
    url, key = get_client_conf(client)
    print(f"🔑 Llamada a TrendMicro para cliente={client} usando URL={url}")

    if not url or not key:
        return {"jsonrpc": "2.0", "id": 1, "error": f"API config missing for client {client}"}

    if request.method == "get_workbench_alerts":
        params = {k: v for k, v in request.params.items() if k != "client"}
        resp = requests.get(
            f"{url}/v3.0/workbench/alerts",
            headers={"Authorization": f"Bearer {key}"},
            params=params
        )
        return {"jsonrpc": "2.0", "id": 1, "result": resp.json()}
    return {"jsonrpc": "2.0", "id": 1, "error": "Method not supported"}
