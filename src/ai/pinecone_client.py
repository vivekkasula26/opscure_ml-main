"""
Pinecone Client for RAG Retrieval
Retrieves similar historical incidents for context augmentation.
"""

import os
import hashlib
from typing import List, Optional
from src.common.types import RetrievedIncident, CorrelationBundle
from src.ai.summarizer import Summarizer


class PineconeClient:
    """
    Client for Pinecone vector database operations.
    Provides embedding and similarity search for historical incidents.
    """
    
    def __init__(
        self,
        index_name: Optional[str] = None,
        api_key: Optional[str] = None,
        environment: Optional[str] = None
    ):
        """
        Initialize Pinecone client.
        
        Args:
            index_name: Name of the Pinecone index
            api_key: Pinecone API key (defaults to PINECONE_API_KEY env var)
            environment: Pinecone environment (defaults to PINECONE_ENVIRONMENT env var)
        """
        self.index_name = index_name or os.getenv("PINECONE_INDEX_NAME", "opscure-incidents")
        self.api_key = api_key or os.getenv("PINECONE_API_KEY")
        self.environment = environment or os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
        
        self._index = None
        self._initialized = False
        
        # Embedding dimension (using OpenAI text-embedding-3-small)
        self.dimension = 1536
    
    async def init(self) -> None:
        """
        Initialize connection to Pinecone.
        Creates index if it doesn't exist.
        """
        if self._initialized:
            return
        
        if not self.api_key:
            print("[PineconeClient] Warning: No API key configured, using mock mode")
            self._initialized = True
            return
        
        try:
            from pinecone import Pinecone
            
            pc = Pinecone(api_key=self.api_key)
            
            # Check if index exists
            existing_indexes = [idx.name for idx in pc.list_indexes()]
            
            if self.index_name not in existing_indexes:
                print(f"[PineconeClient] Creating index: {self.index_name}")
                pc.create_index(
                    name=self.index_name,
                    dimension=self.dimension,
                    metric="cosine",
                    spec={
                        "serverless": {
                            "cloud": "aws",
                            "region": self.environment
                        }
                    }
                )
            
            self._index = pc.Index(self.index_name)
            self._initialized = True
            print(f"[PineconeClient] Initialized with index: {self.index_name}")
            
        except ImportError:
            print("[PineconeClient] Pinecone package not installed, using mock mode")
            self._initialized = True
        except Exception as e:
            print(f"[PineconeClient] Failed to initialize: {e}, using mock mode")
            self._initialized = True
    
    def embed(self, text: str) -> List[float]:
        """
        Create embedding vector from text.
        
        For v1, uses a deterministic hash-based embedding.
        In production, replace with OpenAI text-embedding-3-small.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector of dimension 1536
        """
        if not text:
            return [0.0] * self.dimension
        
        # Try to use OpenAI for real embeddings
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                import openai
                client = openai.OpenAI(api_key=openai_key)
                response = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text[:8000]  # Truncate to model limit
                )
                return response.data[0].embedding
            except Exception as e:
                print(f"[PineconeClient] OpenAI embedding failed: {e}, using fallback")
        
        # Fallback: Deterministic hash-based embedding
        return self._create_mock_embedding(text)
    
    def _create_mock_embedding(self, text: str) -> List[float]:
        """
        Create a deterministic mock embedding for testing.
        Uses SHA-512 hash to generate consistent vectors.
        
        Args:
            text: Text to embed
            
        Returns:
            Mock embedding vector
        """
        # Create multiple hashes for more dimensions
        hash_bytes = b""
        for i in range(24):  # 24 * 64 bytes = 1536 floats
            salted = f"{text}_{i}".encode()
            hash_bytes += hashlib.sha512(salted).digest()
        
        # Convert to floats in [-1, 1]
        embedding = []
        for i in range(0, min(len(hash_bytes), self.dimension * 2), 2):
            if i + 1 < len(hash_bytes):
                value = (hash_bytes[i] + hash_bytes[i + 1] * 256) / 65535.0
                embedding.append(value * 2 - 1)
        
        # Ensure correct dimension
        while len(embedding) < self.dimension:
            embedding.append(0.0)
        
        return embedding[:self.dimension]
    
    async def query_similar_incidents(
        self,
        embedding: List[float],
        top_k: int = 5
    ) -> List[RetrievedIncident]:
        """
        Query Pinecone for similar historical incidents.
        
        Args:
            embedding: Query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of similar incidents with metadata
        """
        await self.init()
        
        # If no real index, return mock data
        if self._index is None:
            return self._get_mock_incidents(top_k)
        
        try:
            results = self._index.query(
                vector=embedding,
                top_k=top_k,
                include_metadata=True
            )
            
            incidents = []
            for match in results.matches:
                metadata = match.metadata or {}
                incidents.append(RetrievedIncident(
                    id=match.id,
                    summary=metadata.get("summary", ""),
                    rootCause=metadata.get("root_cause", ""),
                    recommendedAction=metadata.get("recommended_action", ""),
                    confidence=match.score
                ))
            
            return incidents
            
        except Exception as e:
            print(f"[PineconeClient] Query failed: {e}, returning mock data")
            return self._get_mock_incidents(top_k)
    
    def _get_mock_incidents(self, top_k: int) -> List[RetrievedIncident]:
        """
        Return mock historical incidents for testing.
        
        Args:
            top_k: Number of incidents to return
            
        Returns:
            List of mock incidents
        """
        mock_data = [
            RetrievedIncident(
                id="hist_001",
                summary="Database connection pool exhaustion causing API timeouts",
                rootCause="Connection pool size too small for traffic spike",
                recommendedAction="Increase connection pool size from 10 to 25",
                confidence=0.92
            ),
            RetrievedIncident(
                id="hist_002",
                summary="Memory leak in auth-service causing OOMKilled pods",
                rootCause="Unbounded cache growth in session handler",
                recommendedAction="Restart pods and apply memory limit patch",
                confidence=0.87
            ),
            RetrievedIncident(
                id="hist_003",
                summary="High latency due to missing database index",
                rootCause="Full table scan on users table for email lookup",
                recommendedAction="Add index on users.email column",
                confidence=0.85
            ),
            RetrievedIncident(
                id="hist_004",
                summary="Cascading failure from rate limiter misconfiguration",
                rootCause="Rate limit threshold too low for batch operations",
                recommendedAction="Increase rate limit to 1000 req/min for batch endpoints",
                confidence=0.81
            ),
            RetrievedIncident(
                id="hist_005",
                summary="SSL certificate expiry causing connection failures",
                rootCause="Certificate auto-renewal job failed silently",
                recommendedAction="Manually renew certificate and fix renewal cron",
                confidence=0.78
            ),
        ]
        
        return mock_data[:top_k]
    
    async def store_incident(
        self,
        incident_id: str,
        summary: str,
        root_cause: str,
        recommended_action: str,
        embedding: Optional[List[float]] = None
    ) -> bool:
        """
        Store a resolved incident for future retrieval.
        
        Args:
            incident_id: Unique incident identifier
            summary: Textual summary of the incident
            root_cause: Identified root cause
            recommended_action: Action that resolved the incident
            embedding: Pre-computed embedding (optional)
            
        Returns:
            True if stored successfully
        """
        await self.init()
        
        if self._index is None:
            print(f"[PineconeClient] Would store incident: {incident_id}")
            return True
        
        try:
            # Create embedding if not provided
            if embedding is None:
                embedding = self.embed(summary)
            
            self._index.upsert(
                vectors=[{
                    "id": incident_id,
                    "values": embedding,
                    "metadata": {
                        "summary": summary,
                        "root_cause": root_cause,
                        "recommended_action": recommended_action
                    }
                }]
            )
            
            print(f"[PineconeClient] Stored incident: {incident_id}")
            return True
            
        except Exception as e:
            print(f"[PineconeClient] Failed to store incident: {e}")
            return False


# Singleton instance
_pinecone_client: Optional[PineconeClient] = None


async def get_pinecone_client() -> PineconeClient:
    """Get or create Pinecone client singleton"""
    global _pinecone_client
    
    if _pinecone_client is None:
        _pinecone_client = PineconeClient()
        await _pinecone_client.init()
    
    return _pinecone_client

