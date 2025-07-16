from fastapi import FastAPI
from pydantic import BaseModel
import os, requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta, timezone

app = FastAPI()

class MCPRequest(BaseModel):
    method: str
    params: dict = {}

def get_client_conf(client):
    client = client.upper()
    url = os.getenv(f"{client}_EXABEAM_API") or os.getenv("EXABEAM_API")
    cid = os.getenv(f"{client}_EXABEAM_CLIENT_ID") or os.getenv("EXABEAM_CLIENT_ID")
    secret = os.getenv(f"{client}_EXABEAM_CLIENT_SECRET") or os.getenv("EXABEAM_CLIENT_SECRET")
    return url, cid, secret

def get_token(url, cid, secret):
    resp = requests.post(
        f"{url}/auth/v1/token",
        auth=HTTPBasicAuth(cid, secret),
        data={"grant_type": "client_credentials"}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

@app.post("/")
def handle_mcp(request: MCPRequest):
    client = request.params.get("client", "DEFAULT")
    url, cid, secret = get_client_conf(client)
    if not url or not cid or not secret:
        return {"jsonrpc": "2.0", "id": 1, "error": "API config missing for client"}

    if request.method == "search_anomalies":
        token = get_token(url, cid, secret)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(request.params.get("days", 7)))
        query = request.params.get("query", 'product:"Advanced Analytics" AND alert_source:"anomaly"')
        payload = {
            "query": query,
            "startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "size": request.params.get("size", 1000),
            "offset": 0
        }
        r = requests.post(
            f"{url}/search/v2/events",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload, timeout=30
        )
        return {"jsonrpc": "2.0", "id": 1, "result": r.json()}
    return {"jsonrpc": "2.0", "id": 1, "error": "Method not supported"}
