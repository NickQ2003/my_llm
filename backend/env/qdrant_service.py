import os
import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer
import tiktoken
from dotenv import load_dotenv
from pathlib import Path
import uuid

# Configure logging
logger = logging.getLogger(__name__)

class QdrantService:
    """Service class to handle Qdrant vector database operations for MATEO with persistent memory."""
    
    def __init__(self):
        """Initialize Qdrant client and embedding model."""
        # Load environment variables
        dotenv_path = Path(__file__).resolve().parent / ".env"
        load_dotenv(dotenv_path)
        
        self.qdrant_url = os.getenv("QDRANT_URL")
        if not self.qdrant_url:
            logger.error("❌ QDRANT_URL not set in .env")
            raise ValueError("QDRANT_URL is required in .env file")
        
        # Initialize Qdrant client with persistent connection
        try:
            self.client = QdrantClient(
                url=self.qdrant_url,
                prefer_grpc=False,
                timeout=30
            )
            logger.info("✅ Qdrant connection established")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Qdrant: {e}")
            raise ValueError(f"Failed to connect to Qdrant: {e}")
        
        # Initialize embedding model
        try:
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("✅ Embedding model loaded")
        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            raise ValueError(f"Failed to load embedding model: {e}")
        
        # Collection configuration
        self.collection_name = "mateo_conversations"
        self._initialize_collection()

    def _initialize_collection(self):
        """Create Qdrant collection if it doesn't exist with optimized configuration."""
        try:
            if not self.client.collection_exists(collection_name=self.collection_name):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=384,
                        distance=models.Distance.COSINE,
                        on_disk=True
                    ),
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=0,
                        memmap_threshold=20000
                    )
                )
                logger.info(f"✅ Created Qdrant collection: {self.collection_name}")
            else:
                logger.info(f"✅ Qdrant collection {self.collection_name} already exists")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Qdrant collection: {e}")
            raise

    def store_conversation(self, conversation_id: str, session_id: str, user_message: str, chatbot_response: str, model: str, metadata: Dict[str, Any] = None):
        """Store a conversation in Qdrant with a session_id for tracking and additional metadata."""
        try:
            document = {
                "user_message": user_message,
                "chatbot_response": chatbot_response,
                "model": model,
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            if metadata:
                document.update(metadata)
            
            text_to_embed = f"{user_message} {chatbot_response}"
            embedding = self.embedding_model.encode([text_to_embed])[0]
            
            point = models.PointStruct(
                id=conversation_id,
                vector=embedding.tolist(),
                payload={
                    "document": document,
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "model": model,
                    "timestamp": document["timestamp"],
                    "metadata": metadata or {}
                }
            )
            
            for attempt in range(3):
                try:
                    self.client.upsert(
                        collection_name=self.collection_name,
                        points=[point],
                        wait=True
                    )
                    logger.info(f"✅ Stored conversation {conversation_id} in Qdrant (model: {model}, session: {session_id})")
                    break
                except Exception as e:
                    logger.warning(f"⚠️ Retry {attempt + 1}/3: Failed to store conversation {conversation_id}: {e}")
                    if attempt == 2:
                        raise
        except Exception as e:
            logger.error(f"❌ Failed to store conversation in Qdrant: {type(e).__name__} - {str(e)}")
            raise

    def search_conversations(self, query: str, model: str, session_id: str, limit: int = 15, similarity_threshold: float = 0.3, include_all_sessions: bool = False) -> str:
        """Search for relevant conversations in Qdrant, optionally across all sessions, and return formatted context."""
        try:
            query = query.strip().lower()
            query_embedding = self.embedding_model.encode([query])[0]
            
            # Tokenization setup
            try:
                encoding = tiktoken.encoding_for_model("gpt-4")
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")
            
            # Fetch conversations with vector search
            must_conditions = [
                models.FieldCondition(key="model", match=models.MatchValue(value=model))
            ]
            if session_id and not include_all_sessions:
                must_conditions.append(
                    models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))
                )
            
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding.tolist(),
                query_filter=models.Filter(must=must_conditions),
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            
            points = search_result
            if not points and session_id and not include_all_sessions:
                logger.info(f"No conversations found for model {model} and session {session_id}, trying without session filter")
                search_result = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding.tolist(),
                    query_filter=models.Filter(
                        must=[models.FieldCondition(key="model", match=models.MatchValue(value=model))]
                    ),
                    limit=limit,
                    with_payload=True,
                    with_vectors=False
                )
                points = search_result
            
            if not points:
                logger.warning("⚠️ No conversations found in Qdrant")
                return "No se encontraron conversaciones relevantes en la base de datos."

            # Sort points by timestamp (newest first)
            points = sorted(
                points,
                key=lambda p: p.payload.get('document', {}).get('timestamp', ''),
                reverse=True
            )
            
            total_tokens = 0
            context_lines = []
            max_tokens = 8100
            
            for point in points:
                doc = point.payload.get('document', {})
                user_message = doc.get('user_message', 'N/A')
                chatbot_response = doc.get('chatbot_response', 'N/A')
                timestamp = doc.get('timestamp', 'Sin fecha')
                result_session_id = doc.get('session_id', 'N/A')
                
                context_entry = (
                    f"---\n"
                    f"{'🔹 [SESIÓN ACTUAL]' if result_session_id == session_id else f'🔸 [SESIÓN {result_session_id[:8]}]'}\n"
                    f"👤 **Usuario:** {user_message}\n"
                    f"🤖 **MATEO:** {chatbot_response}\n"
                    f"📅 **Fecha:** {timestamp[:19]}\n"
                )
                
                tokens = len(encoding.encode(context_entry))
                if total_tokens + tokens > max_tokens:
                    logger.info(f"🔄 Token limit of 8100 reached: {total_tokens}/{max_tokens}")
                    break
                    
                context_lines.append(context_entry)
                total_tokens += tokens
            
            context = "".join(context_lines)
            logger.info(f"✅ Context retrieved: {len(context_lines)} conversations, {total_tokens} tokens")
            return context if context else "No se encontraron conversaciones relevantes en la base de datos."
            
        except Exception as e:
            logger.error(f"❌ Error searching in Qdrant: {type(e).__name__} - {str(e)}")
            return "Error al buscar conversaciones en la base de datos."

    def get_conversation_data(self, model: str, session_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """Retrieve comprehensive conversation data from Qdrant."""
        try:
            must_conditions = [
                models.FieldCondition(key="model", match=models.MatchValue(value=model))
            ]
            if session_id:
                must_conditions.append(
                    models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))
                )
            
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(must=must_conditions),
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            
            points = scroll_result[0]
            if not points and session_id:
                logger.info(f"No conversations found for model {model} and session {session_id}, trying without session filter")
                scroll_result = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=models.Filter(
                        must=[models.FieldCondition(key="model", match=models.MatchValue(value=model))]
                    ),
                    limit=limit,
                    with_payload=True,
                    with_vectors=False
                )
                points = scroll_result[0]
            
            conversations = []
            for point in points:
                doc = point.payload.get('document', {})
                conversations.append({
                    "conversation_id": point.payload.get("conversation_id", ""),
                    "session_id": doc.get("session_id", ""),
                    "user_message": doc.get("user_message", ""),
                    "chatbot_response": doc.get("chatbot_response", ""),
                    "timestamp": doc.get("timestamp", ""),
                    "model": doc.get("model", ""),
                    "metadata": point.payload.get("metadata", {})
                })
            
            stats = self.get_conversation_stats(model)
            logger.info(f"✅ Retrieved {len(conversations)} conversations with stats")
            return {
                "conversations": conversations,
                "stats": stats,
                "total_conversations": len(conversations)
            }
            
        except Exception as e:
            logger.error(f"❌ Error retrieving conversation data: {type(e).__name__} - {str(e)}")
            return {"conversations": [], "stats": {}, "total_conversations": 0}

    def get_last_conversation(self, model: str, session_id: Optional[str] = None) -> Tuple[str, str]:
        """Retrieve the last stored conversation for the specified model and session."""
        try:
            must_conditions = [
                models.FieldCondition(key="model", match=models.MatchValue(value=model))
            ]
            if session_id:
                must_conditions.append(
                    models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))
                )
            
            search_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(must=must_conditions),
                limit=1,
                with_payload=True,
                with_vectors=False
            )
            
            points = search_result[0]
            if not points:
                if session_id:
                    logger.info(f"No conversations found for model {model} and session {session_id}, trying without session filter")
                    search_result = self.client.scroll(
                        collection_name=self.collection_name,
                        scroll_filter=models.Filter(
                            must=[models.FieldCondition(key="model", match=models.MatchValue(value=model))]
                        ),
                        limit=1,
                        with_payload=True,
                        with_vectors=False
                    )
                    points = search_result[0]
                
                if not points:
                    logger.info(f"No conversations found for model {model}")
                    return "", ""
            
            last_point = points[0]
            doc = last_point.payload.get("document", {})
            user_message = doc.get("user_message", "")
            chatbot_response = doc.get("chatbot_response", "")
            
            if not user_message and not chatbot_response:
                logger.warning(f"Incomplete data in last conversation for model {model}")
                return "", ""
            
            logger.info(f"✅ Retrieved last conversation for model {model}")
            return user_message, chatbot_response
        except Exception as e:
            logger.error(f"❌ Error retrieving last conversation: {type(e).__name__} - {str(e)}")
            return "", ""

    def get_conversation_history(self, model: str, session_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve a list of recent conversations for the specified model and session."""
        try:
            must_conditions = [
                models.FieldCondition(key="model", match=models.MatchValue(value=model))
            ]
            if session_id:
                must_conditions.append(
                    models.FieldCondition(key="session_id", match=models.MatchValue(value=session_id))
                )
            
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(must=must_conditions),
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            
            points = scroll_result[0]
            if not points and session_id:
                logger.info(f"No conversations found for model {model} and session {session_id}, trying without session filter")
                scroll_result = self.client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=models.Filter(
                        must=[models.FieldCondition(key="model", match=models.MatchValue(value=model))]
                    ),
                    limit=limit,
                    with_payload=True,
                    with_vectors=False
                )
                points = scroll_result[0]
            
            history = []
            for point in points:
                doc = point.payload.get("document", {})
                history.append({
                    "conversation_id": point.payload.get("conversation_id", ""),
                    "session_id": doc.get("session_id", ""),
                    "user_message": doc.get("user_message", ""),
                    "chatbot_response": doc.get("chatbot_response", ""),
                    "timestamp": doc.get("timestamp", ""),
                    "model": doc.get("model", ""),
                    "metadata": point.payload.get("metadata", {})
                })
            
            logger.info(f"✅ Retrieved {len(history)} conversations for history (model: {model})")
            return history
            
        except Exception as e:
            logger.error(f"❌ Error retrieving conversation history: {type(e).__name__} - {str(e)}")
            return []

    def debug_content(self, model: str = "openai", limit: int = 10) -> int:
        """Debug function to inspect stored content in Qdrant."""
        try:
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[models.FieldCondition(key="model", match=models.MatchValue(value=model))]
                ),
                limit=limit,
                with_payload=True
            )
            
            points = scroll_result[0]
            logger.info(f"🔍 DEBUG: {len(points)} conversations found for model {model}")
            
            for point in points[:3]:
                doc = point.payload.get("document", {})
                user_msg = doc.get("user_message", "N/A")[:60] + "..."
                timestamp = doc.get("timestamp", "N/A")[:19]
                session = doc.get("session_id", "N/A")[:8]
                logger.info(f"[{timestamp}] Session {session}: {user_msg}")
            
            return len(points)
            
        except Exception as e:
            logger.error(f"❌ Error debugging Qdrant content: {e}")
            return 0

    def get_conversation_stats(self, model: str = "openai") -> Dict[str, int]:
        """Return statistics about stored conversations."""
        try:
            total_count = self.debug_content(model, limit=100)
            
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[models.FieldCondition(key="model", match=models.MatchValue(value=model))]
                ),
                limit=100,
                with_payload=True
            )
            
            sessions = set()
            for point in scroll_result[0]:
                session_id = point.payload.get('document', {}).get('session_id')
                if session_id:
                    sessions.add(session_id)
            
            logger.info(f"📊 Stats: {total_count} conversations, {len(sessions)} sessions")
            return {"total_conversations": total_count, "unique_sessions": len(sessions)}
            
        except Exception as e:
            logger.error(f"❌ Error getting stats: {e}")
            return {"total_conversations": 0}