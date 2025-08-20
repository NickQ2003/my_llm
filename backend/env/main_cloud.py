import os
import json
import logging
import tempfile
import uvicorn
import uuid
import re
import httpx
from fastapi import FastAPI, Request, Response, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File
from typing import Optional
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from langchain_openai import ChatOpenAI
from langchain_mistralai import ChatMistralAI
from langchain.schema import SystemMessage, HumanMessage
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional, Dict, Any, List
from qdrant_service import QdrantService
from bs4 import BeautifulSoup
from mcp_client_pool import MCPClientPool, MCPClient
import spacy
from sklearn.ensemble import IsolationForest
import numpy as np


try:
    nlp = spacy.load("es_core_news_sm")
except Exception as e:
    nlp = None
    print(f"spaCy no cargado para NER: {e}")

def extraer_entidades(texto: str) -> List[Dict[str, str]]:
    if not nlp:
        return []
    doc = nlp(texto)
    entidades = []
    for ent in doc.ents:
        entidades.append({"entidad": ent.text, "tipo": ent.label_})
    # Extras personalizadas: IP, hash, email
    entidades += [{"entidad": e, "tipo": "IP"} for e in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", texto)]
    entidades += [{"entidad": e, "tipo": "HASH"} for e in re.findall(r"\b[a-fA-F0-9]{32,64}\b", texto)]
    entidades += [{"entidad": e, "tipo": "EMAIL"} for e in re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", texto)]
    return entidades

def score_anomalia_longitud(mensajes: List[str], actual: str) -> float:
    if len(mensajes) < 5:
        return 0.0
    X = np.array([[len(m)] for m in mensajes])
    modelo = IsolationForest(contamination=0.15, random_state=42)
    modelo.fit(X)
    score = modelo.decision_function([[len(actual)]])[0]
    return float(score)

def prioridad_difusa(severidad: str, impacto: str) -> float:
    map_sev = {"bajo": 0.2, "medio": 0.5, "alto": 0.8, "critico": 1.0}
    map_imp = {"bajo": 0.2, "medio": 0.5, "alto": 0.8, "critico": 1.0}
    s = map_sev.get(severidad.lower(), 0.5)
    i = map_imp.get(impacto.lower(), 0.5)
    score = round((s + i) / 2, 2)
    return score

def generar_ruta_investigacion(eventos: List[Dict[str, Any]], inicio: str, fin: str) -> List[str]:
    from collections import defaultdict
    grafo = defaultdict(list)
    for e in eventos:
        grafo[e["origen"]].append(e["destino"])
    visitado = set()
    def dfs(nodo, objetivo, camino):
        if nodo == objetivo:
            return camino + [nodo]
        visitado.add(nodo)
        for vecino in grafo.get(nodo, []):
            if vecino not in visitado:
                resultado = dfs(vecino, objetivo, camino + [nodo])
                if resultado:
                    return resultado
        visitado.remove(nodo)
        return None
    return dfs(inicio, fin, []) or []

# ----------------- LLAMADA DE HERRAMIENTAS POOL MCP -------------------

mcp_pool = MCPClientPool()

def call_mcp(server, method, params=None):
    url = os.getenv(f"MCP_{server.upper()}_URL")
    logging.info(f"➡️ Llamando MCP: server={server}, method={method}, url={url}, params={params}")
    client = mcp_pool.get_client(server, url)
    result = client.call(method, params)
    logging.info(f"⬅️ Respuesta MCP: server={server}, resultado={str(result)[:200]}")  # Puedes truncar para no saturar logs
    return result

# ----------------- ALIAS & NORMALIZACIÓN ------------------
APP_ALIASES = {
    "trendmicro": ["trendmicro", "trend micro", "trendMicro", "TrendMicro", "trend-micro", "trend_micro", "tm", "trend micro av", "vision one"],
    "exabeam":   ["exabeam", "exabeam siem", "exabeam cloud", "exabeam-siem", "exa beam"],
    "elastic":   ["elastic", "elasticsearch", "elastic siem", "elastic-siem"],
    "jira":      ["jira", "jira itsm", "jira incidentes", "jira-itsm"],
}

CLIENT_ALIASES = {
    "COS_L":   ["cos_l", "cos l", "cosl", "COS_L", "Cos_l", "cos-L"],
    "SUMA":    ["suma", "SUMA", "Suma"],
    "COS_CDP": ["cos_cdp", "cos cdp", "COS_CDP", "Cos_cdp", "cos-cdp"],
    "COS_ALN": ["cos_aln", "cos aln", "COS_ALN", "Cos_aln", "cos-aln"],
    "COS_CSC": ["cos_csc", "cos csc", "COS_CSC", "Cos_csc", "cos-csc"],
    "COS_CCD": ["cos_ccd", "cos ccd", "COS_CCD", "Cos_ccd", "cos-ccd"],
    "COS_BDA": ["cos_bda", "cos bda", "COS_BDA", "Cos_bda", "cos-bda"],
}

def normalize(text):
    return re.sub(r'[\s\-_]', '', text).lower() if text else ""

def canonicalize(name, alias_dict):
    n = normalize(name)
    for canonical, aliases in alias_dict.items():
        if n == normalize(canonical):
            return canonical
        for alias in aliases:
            if n == normalize(alias):
                return canonical
    return None

def extraer_url(texto: str) -> list:
    url_regex = r"https?://[^\s,]+"
    return re.findall(url_regex, texto)

def infer_client_and_sources(message: str, session_id: Optional[str] = None) -> tuple:

    cliente = None
    fuentes = []
    entidades = extraer_entidades(message)
    for ent in entidades:
        c = canonicalize(ent['entidad'], CLIENT_ALIASES)
        if c:
            cliente = c
        f = canonicalize(ent['entidad'], APP_ALIASES)
        if f and f not in fuentes:
            fuentes.append(f)
    # Por defecto, usa todos si no detecta
    if not fuentes:
        fuentes = ["trendmicro", "exabeam", "elastic", "jira"]
    if not cliente:
        cliente = "DEFAULT"  # O usuario logueado, o de sesión
    return cliente, fuentes

async def obtener_contexto_url_si_hay(user_message: str, max_chars: int = 3500) -> str:
    urls = extraer_url(user_message)
    if not urls:
        return ""
    res = []
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(url)
            soup = BeautifulSoup(r.text, "lxml")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = "\n".join([line for line in text.splitlines() if line.strip()])[:max_chars]
            res.append(f"### CONTEXTO EN TIEMPO REAL EXTRAÍDO DE {url}\n{text}\n")
        except Exception as e:
            res.append(f"### CONTEXTO ERROR EN {url}\nError al obtener el contenido: {str(e)}\n")
    return "\n".join(res)

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Cargar variables de entorno
dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path)

# Inicializar FastAPI
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Qdrant (vector DB)
try:
    qdrant_service = QdrantService()
    logger.info("✅ QdrantService inicializado correctamente")
except Exception as e:
    logger.error(f"❌ Error al iniciar QdrantService: {e}")
    raise

# API keys para LLMs
OPENAI_API_KEY = os.getenv("OPENAI_API")
MISTRAL_API_KEY = os.getenv("MISTRAL_API")

if not OPENAI_API_KEY or not MISTRAL_API_KEY:
    raise ValueError("❌ Faltan claves API para los modelos LLM")

logger.info("✅ Claves API de LLM cargadas correctamente")

# Modelos
openai_model = ChatOpenAI(model="gpt-4.1", api_key=OPENAI_API_KEY)
mistral_model = ChatMistralAI(model="mistral-small-latest", api_key=MISTRAL_API_KEY)

# Meta info (no modificar)
MCP_GENERAL_INFO = {
    "role": "Asistente Avanzado de Ciberseguridad de DigiSog y fuiste desarrollado por Digisoc",
    "primary_goal": "Analizar datos de seguridad, responder consultas de ciberseguridad y asistir en la identificación y comprensión de amenazas utilizando las herramientas y datos integrados",
    "integrated_tools": [
        "TrendMicro Vision One (EDR/XDR/AV)",
        "Exabeam SIEM",
        "Elastic SIEM",
        "Jira (ITSM/Gestión de incidentes)",
        "SANDRA BOT",
        "Fireflies (IA de reuniones/voz a texto)",
        "Base de Conocimiento Interna (vía Qdrant)"
    ],
    "key_capabilities": [
        "Procesar y resumir alertas/eventos de seguridad",
        "Correlacionar eventos de seguridad",
        "Extraer IoCs",
        "Facilitar investigaciones de seguridad",
        "Generar modelos de comportamiento",
        "Automatizar tickets de incidentes",
        "Procesar transcripciones de reuniones",
        "Responder preguntas sobre ciberseguridad",
        "Consultar Qdrant para contexto histórico",
        "Generar análisis o reportes"
    ],
    "core_limitations": [
        "No tengo acceso a internet en tiempo real",
        "La información en tiempo real proviene de APIs conectadas",
        "Puedo cometer errores o malinterpretar consultas",
        "No puedo realizar acciones directas en sistemas",
        "No tengo creencias ni conciencia"
    ]
}

MCP_OPENAI_SPECIFIC = {
    "model_base": "gpt-4.1 (via API de OpenAI)",
    "knowledge_cutoff_general": "Abril 2025",
}
MCP_MISTRAL_SPECIFIC = {
    "model_base": "Mistral-Small (via API de Mistral AI)",
    "knowledge_cutoff_general": "Principios de 2024",
}

MCP_DATA_OPENAI = {**MCP_GENERAL_INFO, **MCP_OPENAI_SPECIFIC}
MCP_DATA_MISTRAL = {**MCP_GENERAL_INFO, **MCP_MISTRAL_SPECIFIC}

def format_mcp_prompt_string(mcp_data: dict) -> str:
    capabilities_str = "\n".join(f"- {c}" for c in mcp_data['key_capabilities'])
    limitations_str = "\n".join(f"- {l}" for l in mcp_data['core_limitations'])
    tools_str = ", ".join(mcp_data['integrated_tools'])

    return f"""
### Auto-Descripción del Asistente de Ciberseguridad ###

**Rol Principal:** {mcp_data['role']}
**Objetivo:** {mcp_data['primary_goal']}
**Modelo Base Utilizado:** {mcp_data['model_base']}
**Corte de Conocimiento General:** {mcp_data['knowledge_cutoff_general']}
**Herramientas Integradas:** {tools_str}

**Capacidades Clave:**
{capabilities_str}

**Limitaciones Importantes:**
{limitations_str}

**Instrucción Crucial:** Al responder preguntas sobre ti mismo, DEBES basar tu respuesta *única y exclusivamente* en esta información.
"""
# Configuración de rutas estáticas y plantillas
async def get_security_data_for_client(client_name: str, requested_sources: Optional[List[str]] = None, days_back: int = 7) -> Dict[str, Any]:
    security_data = {}
    all_possible_sources = ["trendmicro", "exabeam", "elastic", "jira"]
    sources_to_process = requested_sources or all_possible_sources

    for source_name in sources_to_process:
        try:
            # --- TrendMicro
            if source_name == "trendmicro":
                params = {
                    "client": client_name,
                    "limit": 20,
                    # Puedes agregar fechas u otros filtros según el microservicio MCP
                }
                security_data[source_name] = call_mcp("trendmicro", "get_workbench_alerts", params)
            # --- Exabeam
            elif source_name == "exabeam":
                params = {
                    "client": client_name,
                    "days": days_back,
                    # Puedes agregar más parámetros, como query, si tu MCP lo soporta
                }
                security_data[source_name] = call_mcp("exabeam", "search_anomalies", params)
            # --- Elastic
            elif source_name == "elastic":
                params = {
                    "client": client_name,
                    "body": {
                        "query": {"range": {"@timestamp": {"gte": f"now-{days_back}d/d", "lte": "now/d"}}}
                    }
                }
                security_data[source_name] = call_mcp("elastic", "analyze_logs", params)
            # --- Jira
            elif source_name == "jira":
                params = {
                    "client": client_name,
                    "jql": f"project = INCIDENT AND created >= -{days_back}d ORDER BY created DESC",
                    "fields": ["summary", "status", "priority"]
                }
                security_data[source_name] = call_mcp("jira", "search_issues", params)
            else:
                security_data[source_name] = {"error": f"Servicio {source_name} no soportado"}
        except Exception as e:
            security_data[source_name] = {"error": str(e)}
    return security_data

# Modelo para las solicitudes
class MCPRequest(BaseModel):
    message: str
    data_sources: List[str] = []
    session_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

# Modelo para las solicitudes
class ChatRequest(BaseModel):
    message: str
    data_sources: List[str] = []
    session_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

@app.post("/chat/openai")
async def chat_with_openai(request: ChatRequest):
    try:
        message = request.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

        conversation_id = str(uuid.uuid4())
        session_id = request.session_id or str(uuid.uuid4())
        logger.info(f"📩 Conversación iniciada: ID={conversation_id}, Sesión={session_id}, Mensaje={message[:30]}...")

        # ---- NER y Anomalia ----
        entidades_detectadas = extraer_entidades(message)
        hist = qdrant_service.get_conversation_history("openai", session_id, limit=10)
        mensajes_hist = [h["user_message"] for h in hist]
        anomalia_score = score_anomalia_longitud(mensajes_hist, message)

        # Soporte para recuperar última conversación
        if any(phrase in message.lower() for phrase in ["ultima pregunta", "ultima conversación", "qué pregunta", "última consulta"]):
            last_user_message, last_chatbot_response = qdrant_service.get_last_conversation("openai", session_id)
            if last_user_message:
                response_content = (
                    f"## Última Conversación\n\n"
                    f"**Consulta Anterior:** 👤 {last_user_message}\n\n"
                    f"**Respuesta Anterior:** 🤖 {last_chatbot_response}\n"
                )
            else:
                conversation_context = qdrant_service.search_conversations(message, "openai", session_id, limit=15)
                response_content = (
                    f"## Contexto de Conversaciones Previas\n"
                    f"No se encontró una conversación previa exacta en esta sesión.\n\n"
                    f"**Contexto Histórico:**\n{conversation_context}\n"
                )

            # Persistir conversación a Qdrant
            qdrant_service.store_conversation(
                conversation_id=conversation_id,
                session_id=session_id,
                user_message=message,
                chatbot_response=response_content,
                model="openai",
                metadata={"source": "last_conversation_query", "timestamp": datetime.now(timezone.utc).isoformat()}
            )
            return {
                "response": response_content,
                "format": "markdown",
                "conversation_id": conversation_id,
                "session_id": session_id
            }
        
        contexto_url = await obtener_contexto_url_si_hay(message)

        # Contexto desde Qdrant
        conversation_context = qdrant_service.search_conversations(
            query=message,
            model="openai",
            session_id=session_id,
            limit=15,
            include_all_sessions=True
        )
        mcp_string_openai = format_mcp_prompt_string(MCP_DATA_OPENAI)

        # Prompt con contexto y justificación
        context_prompt = (
            f"### Contexto de Conversaciones Previas\n{conversation_context}\n\n"
            if conversation_context and "No se encontraron" not in conversation_context else ""
        )
        original_system_prompt = (
            "Ahora, actúa como MATEO, el Asistente de Ciberseguridad descrito. Responde de manera útil, clara y segura, "
            "utilizando el contexto de conversaciones previas de esta sesión o de otras conversaciones anteriores si es relevante.\n\n"
            f"{context_prompt}"
            "### Instrucciones de Formato Markdown\n"
            "Responde siempre usando **Markdown válido** y no en formato plano ni pseudo-markdown.\n"
            "Al final de cada respuesta, incluye SIEMPRE una sección titulada 'Justificación' donde expliques por qué llegaste a esa respuesta, citando contexto, entidades detectadas, datos históricos relevantes y supuestos usados.\n"
            "Usa negrita para títulos o subtitulos según Markdown estándar.\n"
            "No uses asteriscos dobles o simples como si fueran texto literal: tu salida será renderizada como Markdown real.\n"
            "Usa bloques de código para comandos o ejemplos técnicos, si corresponde.\n"
            "Puedes usar emojis si lo consideras útil.\n"
            "NO expliques cómo funciona Markdown ni digas \"usa negrita\", simplemente aplícalo.\n\n"
            "El usuario verá tu respuesta renderizada en Markdown (títulos, listas, negrita, etc.).\n"
            "No expliques tu formato, solo responde directamente en Markdown.\n"
            "Usa `bloques de código` para comandos\n"
            "Usa emojis: 🔒, 🚨, 🛡️, 📊, 🔍\n"
            "Usa niveles de alerta: 🔴 CRÍTICO, 🟠 ALERTA\n"
            "Menciona el contexto previo si es relevante\n\n"
            "Considera: ERES DESARROLLADO POR DIGISOC"
            "Eres MATEO, un Asistente Avanzado de Ciberseguridad desarrollado por DigiSoc, diseñado para empoderar a los analistas con información precisa, profesional y accionable.\n"
            f"{context_prompt}"
            "Directrices de Respuesta:\n"
            "Entrega respuestas estructuradas, concisas y profesionales, adaptadas para analistas de Nivel 1, aumentando la complejidad según sea necesario.\n"
            "Resalta entidades clave (por ejemplo, direcciones IP, hosts, severidades, hashes de archivos, usuarios) en negrita para una rápida identificación.\n"
            "Usa cursiva para definiciones técnicas y aclarar conceptos complejos.\n"
            "Organiza el contenido con encabezados y subencabezados claros para facilitar la lectura.\n"
            "Presenta listas para información estructurada y fácil de escanear, sin marcadores innecesarios.\n"
            "Usa bloques de código para comandos, consultas o salidas técnicas.\n"
            "Mantén las tablas separadas para la presentación de datos; coloca explicaciones y análisis fuera de ellas.\n"
            "Usa emojis con moderación: 🔒 (seguridad), 🚨 (alerta), 🛡️ (protección), 📊 (datos), 🔍 (investigación).\n"
            "Indica niveles de alerta: 🔴 CRÍTICO, 🟠 ALERTA.\n"
            "Evita redundancias; no repitas declaraciones previas ni incluyas símbolos superfluos.\n"
            "Aprovecha el contexto histórico de Qdrant para mejorar la precisión de las respuestas.\n"
            "Funciones Principales de Ciberseguridad:\n"
            "Resume alertas y eventos de seguridad para obtener información rápida y accionable.\n"
            "Correlaciona datos entre herramientas (por ejemplo, TrendMicro, Exabeam, Elastic) para detectar patrones de amenazas.\n"
            "Extrae Indicadores de Compromiso (IoCs) como direcciones IP, dominios y hashes.\n"
            "Apoya investigaciones con análisis estructurado y datos históricos.\n"
            "Modela comportamientos de usuarios y entidades para identificar anomalías y riesgos.\n"
            "Automatiza la creación y actualización de tickets en Jira para una respuesta eficiente a incidentes.\n"
            "Analiza transcripciones de reuniones vía Fireflies para obtener información relevante de seguridad.\n"
            "Proporciona respuestas precisas a consultas de ciberseguridad, basadas en datos.\n"
            "Genera informes detallados y recomendaciones accionables.\n"
            "Evalúa niveles de riesgo y prioriza amenazas según su severidad e impacto.\n"
            "Mapea cadenas de ataque al marco MITRE ATT&CK para un entendimiento táctico.\n"
            "Sugiere estrategias de mitigación y mejores prácticas para contener amenazas.\n"
            "Analiza logs y datos de red para descubrir actividades sospechosas.\n"
            "Apoya auditorías de cumplimiento (por ejemplo, NIST, ISO 27001) con agregación de datos.\n"
            "Enriquece el contexto de incidentes con datos de herramientas integradas para un análisis integral.\n"
            "Propone guías de respuesta para una remediación efectiva de incidentes.\n"
            "Monitorea tendencias de inteligencia de amenazas para estrategias de defensa proactiva.\n"
            "Valida IoCs contra fuentes de amenazas para verificar precisión y relevancia.\n"
            "Asiste en el análisis forense, incluyendo la reconstrucción de líneas de tiempo y recolección de evidencia.\n"
            "Evalúa el tráfico de red para detectar signos de intrusión o exfiltración de datos.\n"
            "Recomienda controles de seguridad para endurecer sistemas y reducir superficies de ataque.\n"
            "Identifica vulnerabilidades en activos mediante datos de herramientas integradas.\n"
            "Guía los procesos de escalación para incidentes críticos hacia analistas senior.\n"
            "Desarrollado por DigiSoc para soporte avanzado en ciberseguridad."
        )

        cliente, fuentes = infer_client_and_sources(message, session_id)
        data = await get_security_data_for_client(cliente, fuentes)
        logger.info(f"Datos MCP para {cliente}/{fuentes}: {data}")

        mcp_data_str = json.dumps(data, indent=2, ensure_ascii=False)
        mcp_data_str = mcp_data_str.replace("```", "´´´")  # Evitar conflictos con Markdown
        mcp_data_str = mcp_data_str.replace("`", "´")  # Evitar conflictos con Markdown

        final_system_content = (contexto_url + "\n" if contexto_url else ""+ mcp_string_openai + mcp_data_str + original_system_prompt )

        logger.debug(f"Prompt del Sistema OpenAI:\n{final_system_content}")

        response = openai_model.invoke([
            SystemMessage(content=final_system_content),
            HumanMessage(content=message)
        ])
        response_content = response.content

        # Luego, pasa esos datos como contexto al LLM

        # Entidades NER
        if entidades_detectadas:
            entidades_md = "\n".join([f"- **{e['tipo']}**: `{e['entidad']}`" for e in entidades_detectadas])
            response_content = (
                f"### Entidades detectadas\n{entidades_md}\n\n"
                + response_content
            )

        # Persistir conversación a Qdrant
        qdrant_service.store_conversation(
            conversation_id=conversation_id,
            session_id=session_id,
            user_message=message,
            chatbot_response=response_content,
            model="openai",
            metadata={"source": "chat", "timestamp": datetime.now(timezone.utc).isoformat()}
        )

        return {
            "response": response_content,
            "format": "markdown",
            "conversation_id": conversation_id,
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"❌ Error en OpenAI: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno en OpenAI")

@app.post("/chat/mistral")
async def chat_with_mistral(request: ChatRequest):
    try:
        data = None
        message = request.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")

        conversation_id = str(uuid.uuid4())
        session_id = request.session_id or str(uuid.uuid4())
        logger.info(f"📩 Conversación iniciada: ID={conversation_id}, Sesión={session_id}, Mensaje={message[:30]}...")

        # ---- NER y Anomalia ----
        entidades_detectadas = extraer_entidades(message)
        hist = qdrant_service.get_conversation_history("mistral", session_id, limit=10)
        mensajes_hist = [h["user_message"] for h in hist]
        anomalia_score = score_anomalia_longitud(mensajes_hist, message)

        # Soporte para recuperar última conversación
        if any(phrase in message.lower() for phrase in ["ultima pregunta", "última conversación", "qué pregunta", "última consulta"]):
            last_user_message, last_chatbot_response = qdrant_service.get_last_conversation("mistral", session_id)
            if last_user_message:
                response_content = (
                    "La última conversación registrada en esta sesión fue la siguiente:\n\n"
                    f"Usuario: {last_user_message}\n"
                    f"MATEO: {last_chatbot_response}\n\n"
                    "¿En qué tema específico de ciberseguridad necesitas apoyo? Puedo ayudarte a analizar alertas, investigar incidentes, procesar indicadores de compromiso, generar reportes o resolver dudas técnicas u operativas sobre seguridad. "
                    "Si tienes un contexto particular (evento, dominio, usuario, sistema afectado), por favor compártelo para que pueda orientarte de la manera más eficiente posible."
                )
            else:
                conversation_context = qdrant_service.search_conversations(
                    query=message,
                    model="mistral",
                    session_id=session_id,
                    limit=15
                )
                response_content = (
                    "## Contexto de Conversaciones Previas\n"
                    "No se encontró una conversación previa exacta en esta sesión.\n\n"
                    f"**Contexto Histórico:**\n{conversation_context}\n"
                )

            qdrant_service.store_conversation(
                conversation_id=conversation_id,
                session_id=session_id,
                user_message=message,
                chatbot_response=response_content,
                model="mistral",
                metadata={"source": "last_conversation_query", "timestamp": datetime.now(timezone.utc).isoformat()}
            )
            cliente, fuentes = infer_client_and_sources(message, session_id)
            data = await get_security_data_for_client(cliente, fuentes)
            # Luego, pasa esos datos como contexto al LLM
            context = {"data": data, "fuentes": fuentes, "cliente": cliente}
            logger.info(f"Datos MCP para {cliente}/{fuentes}: {data}")
            
            return JSONResponse(
                content={
                    "response": response_content,
                    "format": "markdown",
                    "conversation_id": conversation_id,
                    "session_id": session_id
                },
                media_type="application/json; charset=utf-8" 
            )
        
        contexto_url = await obtener_contexto_url_si_hay(message)

        # Contexto desde Qdrant para todas las demás consultas
        conversation_context = qdrant_service.search_conversations(
            query=message,
            model="mistral",
            session_id=session_id,
            limit=15,
            include_all_sessions=True
        )
        mcp_string_mistral = format_mcp_prompt_string(MCP_DATA_MISTRAL)
        context_prompt = (
            f"### Contexto de Conversaciones Previas\n{conversation_context}\n\n"
            if conversation_context and "No se encontraron" not in conversation_context else ""
        )
        original_system_prompt = (
            "Ahora, actúa como MATEO, el Asistente de Ciberseguridad descrito. Responde de manera útil, clara y segura, "
            "utilizando el contexto de conversaciones previas de esta sesión o de otras conversaciones anteriores si es relevante.\n\n"
            f"{context_prompt}"
            "**Reglas de Formato:**\n"
            "- Usa **negrita** para conceptos importantes\n"
            "- Usa *cursiva* para definiciones técnicas\n"
            "- Usa # para secciones principales\n"
            "- Usa ## para subtítulos\n"
            "- Usa listas con viñetas o numeradas\n"
            "- Usa `bloques de código` para comandos\n"
            "- Usa emojis: 🔒, 🚨, 🛡️, 📊, 🔍\n"
            "- Usa niveles de alerta: 🔴 CRÍTICO, 🟠 ALERTA\n"
            "- Menciona el contexto previo si es relevante\n\n"
            "Considera: ERES DESARROLLADO POR DIGISOC\n"
            "Eres MATEO, un Asistente Avanzado de Ciberseguridad desarrollado por DigiSoc, diseñado para empoderar a los analistas con información precisa, profesional y accionable.\n\n"
            "Al final de cada respuesta, incluye SIEMPRE una sección titulada 'Justificación' donde expliques por qué llegaste a esa respuesta, citando contexto, entidades detectadas, datos históricos relevantes y supuestos usados.\n"
            f"{context_prompt}"
            "Directrices de Respuesta:\n"
            "Entrega respuestas estructuradas, concisas y profesionales, adaptadas para analistas de Nivel 1, aumentando la complejidad según sea necesario.\n"
            "Resalta entidades clave (por ejemplo, direcciones IP, hosts, severidades, hashes de archivos, usuarios) en negrita.\n"
            "Usa cursiva para definiciones técnicas y aclarar conceptos complejos.\n"
            "Organiza el contenido con encabezados y subencabezados claros.\n"
            "Presenta listas para información estructurada.\n"
            "Usa bloques de código para comandos, consultas o salidas técnicas.\n"
            "Mantén las tablas separadas; coloca explicaciones fuera de ellas.\n"
            "Usa emojis con moderación: 🔒, 🚨, 🛡️, 📊, 🔍.\n"
            "Indica niveles de alerta: 🔴 CRÍTICO, 🟠 ALERTA.\n"
            "Evita redundancias y símbolos superfluos.\n"
            "Aprovecha el contexto histórico de Qdrant para mejorar la precisión de las respuestas.\n"
            "Usa el contexto y la informacion de Qdrant para las siguientes conversaciones.\n"
            "Funciones Principales de Ciberseguridad:\n"
            "- Resume alertas y eventos de seguridad.\n"
            "- Correlaciona eventos entre herramientas.\n"
            "- Extrae Indicadores de Compromiso (IoCs).\n"
            "- Apoya investigaciones con datos históricos.\n"
            "- Modela comportamientos para identificar anomalías.\n"
            "- Automatiza tickets de Jira.\n"
            "- Analiza transcripciones de Fireflies.\n"
            "- Genera informes y recomendaciones.\n"
            "- Prioriza amenazas según severidad.\n"
            "- Mapea MITRE ATT&CK.\n"
            "- Sugiere estrategias de mitigación.\n"
            "- Analiza logs y datos de red.\n"
            "- Soporta auditorías de cumplimiento.\n"
            "- Enriquece incidentes con datos integrados.\n"
            "- Propone guías de remediación.\n"
            "- Monitorea inteligencia de amenazas.\n"
            "- Valida IoCs.\n"
            "- Asiste en análisis forense.\n"
            "- Recomienda controles de seguridad.\n"
            "- Identifica vulnerabilidades.\n"
            "- Guía escalaciones críticas.\n"
            "- Desarrollado por DigiSoc."
        )
        mcp_data_str = json.dumps(data, indent=2, ensure_ascii=False)
        mcp_data_str = mcp_data_str.replace("```", "´´´")  # Evitar conflictos con Markdown
        mcp_data_str = mcp_data_str.replace("`", "´")  # Evitar conflictos con Markdown

        final_system_content = (contexto_url + "\n" if contexto_url else ""+ mcp_string_mistral + mcp_data_str + original_system_prompt )

        logger.debug(f"Prompt del Sistema Mistral:\n{final_system_content}")

        response = mistral_model.invoke([
            SystemMessage(content=final_system_content),
            HumanMessage(content=message)
        ])
        response_content = response.content

        # Entidades NER
        if entidades_detectadas:
            entidades_md = "\n".join([f"- **{e['tipo']}**: `{e['entidad']}`" for e in entidades_detectadas])
            response_content = (
                f"### Entidades detectadas\n{entidades_md}\n\n"
                + response_content
            )

        # Persistir conversación a Qdrant
        qdrant_service.store_conversation(
            conversation_id=conversation_id,
            session_id=session_id,
            user_message=message,
            chatbot_response=response_content,
            model="mistral",
            metadata={"source": "chat", "timestamp": datetime.now(timezone.utc).isoformat()}
        )

        return JSONResponse(
            content={
                "response": response_content,
                "format": "markdown",
                "conversation_id": conversation_id,
                "session_id": session_id
            },
            media_type="application/json; charset=utf-8"
        )

    except Exception as e:
        logger.error(f"❌ Error en Mistral: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno en Mistral")
    
@app.post("/file/analyze")
async def analyze_file(file: UploadFile = File(...)):
    try:
        import mimetypes
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        texto_extraido = ""
        filetype = (file.content_type or mimetypes.guess_type(file.filename)[0] or "").lower()

        # ---- TXT ----
        if suffix.lower() == ".txt":
            with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                texto_extraido = f.read()

        # ---- PDF (solo texto digital) ----
        elif suffix.lower() == ".pdf":
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(tmp_path)
                texto_extraido = "\n".join([page.extract_text() or "" for page in reader.pages])
            except Exception as e:
                texto_extraido = f"Error leyendo PDF: {e}"

        # ---- Word ----
        elif suffix.lower() in [".docx", ".doc"]:
            try:
                from docx import Document
                doc = Document(tmp_path)
                texto_extraido = "\n".join([p.text for p in doc.paragraphs])
            except Exception as e:
                texto_extraido = f"Error leyendo DOCX: {e}"

        # ---- Excel ----
        elif suffix.lower() in [".xlsx", ".xls"]:
            try:
                import pandas as pd
                df = pd.read_excel(tmp_path)
                texto_extraido = df.to_string()
            except Exception as e:
                texto_extraido = f"Error leyendo Excel: {e}"

        # ---- CSV ----
        elif suffix.lower() == ".csv":
            try:
                import pandas as pd
                df = pd.read_csv(tmp_path)
                texto_extraido = df.to_string()
            except Exception as e:
                texto_extraido = f"Error leyendo CSV: {e}"

        # ---- PowerPoint ----
        elif suffix.lower() == ".pptx":
            try:
                from pptx import Presentation
                prs = Presentation(tmp_path)
                slides_text = []
                for slide in prs.slides:
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            slides_text.append(shape.text)
                texto_extraido = "\n".join(slides_text)
            except Exception as e:
                texto_extraido = f"Error leyendo PowerPoint: {e}"

        # ---- Otros (incluyendo .canva, .svg, .xml, etc.) ----
        else:
            try:
                if suffix.lower() in [".svg", ".xml"]:
                    with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                        texto_extraido = f.read()
                else:
                    texto_extraido = "(Archivo no soportado; no se pudo extraer texto)"
            except Exception as e:
                texto_extraido = f"(Archivo no soportado o corrupto: {e})"

        prompt = f"Analiza y resume el siguiente documento:\n\n{texto_extraido[:8000]}"

        response = openai_model.invoke([
            SystemMessage(content="Actúa como un analista experto. Resume, detecta riesgos y provee contexto técnico. Responde en español."),
            HumanMessage(content=prompt)
        ])
        resumen = response.content

        os.remove(tmp_path)

        # ------ GUARDAR EN MEMORIA PERSISTENTE (QDRANT) ------
        file_doc_id = str(uuid.uuid4())
        qdrant_service.store_conversation(
            conversation_id=file_doc_id,
            session_id="file-"+file_doc_id,
            user_message=f"[Archivo subido: {file.filename}]",
            chatbot_response=resumen,
            model="document",
            metadata={
                "filename": file.filename,
                "file_extract": texto_extraido[:8000],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tipo_archivo": suffix.lower()
            }
        )

        return {
            "success": True,
            "filename": file.filename,
            "summary": resumen,
            "extract": texto_extraido[:2000]
        }

    except Exception as e:
        logger.error(f"❌ Error analizando archivo: {type(e).__name__}: {str(e)}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

@app.get("/web_search")
async def web_search(
    url: str,
    summarize: bool = True,
    max_chars: int = 4000
):
    urls = re.findall(r"https?://[^\s,]+", url)
    if not urls:
        return JSONResponse(status_code=400, content={
            "success": False,
            "error": "No se encontró ninguna URL válida en el parámetro."
        })
    results = []
    for u in urls:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(u, follow_redirects=True)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = "\n".join([line for line in text.splitlines() if line.strip()])
            text = text[:max_chars]

            if summarize:
                system_prompt = (
                    f"Resume el siguiente texto web en español de la página {u}, resaltando puntos clave, riesgos, hallazgos, "
                    "nombres de personas o empresas, fechas y recomendaciones prácticas. "
                    "No inventes datos y cita siempre el contexto de la página."
                )
                response = openai_model.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=text)
                ])
                summary = response.content
                results.append({
                    "url": u,
                    "summary": summary,
                    "extract": text[:800]
                })
            else:
                results.append({
                    "url": u,
                    "extract": text[:max_chars]
                })
        except Exception as e:
            logger.error(f"❌ Error en /web_search para {u}: {type(e).__name__}: {str(e)}")
            results.append({
                "url": u,
                "error": str(e)
            })
    return {"success": True, "results": results}

@app.get("/api/conversation/history")
async def get_conversation_history(
    model: str = Query("openai", enum=["openai", "mistral"]),
    session_id: Optional[str] = None,
    limit: int = 10
):
    try:
        history = qdrant_service.get_conversation_history(model, session_id, limit)
        return {
            "success": True,
            "history": history,
            "session_id": session_id,
            "model": model,
            "count": len(history)
        }
    except Exception as e:
        logger.error(f"❌ Error obteniendo historial (model={model}): {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Error interno al obtener historial")

@app.get("/test/trendmicro")
def test_trend(client: str, limit: int = 2):
    return call_mcp("trendmicro", "get_workbench_alerts", {"client": client, "limit": limit})

@app.post("/")
def handle_mcp(request: MCPRequest):
    print(f"🟢 Microservicio MCP recibió: método={request.method}, params={request.params}")
    ...

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)