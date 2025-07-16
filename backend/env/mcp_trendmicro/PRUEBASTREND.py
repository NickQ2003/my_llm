import os, requests
from datetime import datetime, timedelta, timezone
import json

BASE = 'https://api.xdr.trendmicro.com'
PATH = '/v3.0/workbench/alerts'
#TOKEN = "TOKEN"  # Asegúrate de definir tu token aquí
now = datetime.now(timezone.utc)
 
start_dt = now - timedelta(days=7)  # 7 días atrás
end_dt = now  # ahora

params = {
    "eventType": "WorkbenchAlert",
    "startDateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "endDateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "dateTimeTarget": "updatedDateTime",  # <- ahora sí alineado a la API
    "limit": 100,
    "orderBy": "severity desc",
}
headers = {
    "Authorization": f"Bearer {TOKEN}",
}


all_alerts = []
while True:
    resp = requests.get(BASE + PATH, params=params, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    print(json.dumps(data, indent=2))  # Añade esto para inspección
    items = data.get('alerts') or data.get('data')
    if not items:
        print("No se encontraron alertas.")
        break
    token = data.get('nextPageToken')
    if not token:
        break

    params['nextPageToken'] = token  # preparar siguiente página
    # opcional: sleep o control de rate-limit

print(f"Total de alertas obtenidas: {len(all_alerts)}")
for alert in all_alerts:
    print(f"ID: {alert['id']}, Severidad: {alert['severity']}, Estado: {alert['status']}")
    # Aquí puedes procesar cada alerta según tus necesidades