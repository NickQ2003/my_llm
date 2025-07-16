from fastapi import FastAPI
from pydantic import BaseModel
import os, requests
from requests.auth import HTTPBasicAuth

app = FastAPI()

class MCPRequest(BaseModel):
    method: str
    params: dict = {}

def get_client_conf(client):
    client = client.upper()
    url = os.getenv(f"{client}_JIRA_API") or os.getenv("JIRA_API")
    email = os.getenv(f"{client}_JIRA_EMAIL") or os.getenv("JIRA_EMAIL")
    token = os.getenv(f"{client}_JIRA_TOKEN") or os.getenv("JIRA_TOKEN")
    return url, email, token

@app.post("/")
def handle_mcp(request: MCPRequest):
    client = request.params.get("client", "DEFAULT")
    url, email, token = get_client_conf(client)
    if not url or not email or not token:
        return {"jsonrpc": "2.0", "id": 1, "error": "API config missing for client"}

    if request.method == "search_issues":
        jql = request.params.get("jql", "project = INCIDENT ORDER BY created DESC")
        fields = request.params.get("fields", ["summary", "status", "priority"])
        params = {"jql": jql, "fields": ",".join(fields)}
        r = requests.get(
            f"{url}/search",
            auth=HTTPBasicAuth(email, token),
            params=params
        )
        return {"jsonrpc": "2.0", "id": 1, "result": r.json()}
    return {"jsonrpc": "2.0", "id": 1, "error": "Method not supported"}
