"""
Ollama Client with Fallback Logic
Handles AI model inference with retry and fallback strategies.
"""

import os
import asyncio
import aiohttp
from typing import Optional
from dataclasses import dataclass


@dataclass
class ModelConfig:
    """Configuration for a model"""
    name: str
    timeout: int = 60
    temperature: float = 0.3
    max_tokens: int = 5000


class OllamaClient:
    """
    Client for Ollama API with multi-model fallback support.
    
    Retry Logic:
    1. Try primary model (gpt-oss)
    2. On error → retry twice
    3. If still failing → fallback to llama3.1:70b
    4. If failing again → fallback to mixtral
    5. If all fail → return degraded JSON
    """
    
    # Model configuration
    PRIMARY_MODEL = ModelConfig(name="llama3.2", timeout=90)
    FALLBACK_1 = ModelConfig(name="phi3:mini", timeout=90)
    FALLBACK_2 = ModelConfig(name="mixtral", timeout=90)
    
    # Degraded response when all models fail
    DEGRADED_RESPONSE = """{
  "root_cause": "unknown",
  "causal_chain": [],
  "auto_heal_candidate": false,
  "recommended_action": {
    "action": "none",
    "target": ""
  },
  "confidence": 0.0
}"""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        primary_model: Optional[str] = None,
        fallback_1: Optional[str] = None,
        fallback_2: Optional[str] = None
    ):
        """
        Initialize Ollama client.
        
        Args:
            base_url: Ollama API URL (defaults to OLLAMA_URL env var)
            api_key: Optional API Key for authenticated endpoints (defaults to OLLAMA_API_KEY)
            primary_model: Override primary model name
            fallback_1: Override first fallback model
            fallback_2: Override second fallback model
        """
        self.base_url = base_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY")

        
        # Allow model overrides from Env or Args
        env_model = os.getenv("OLLAMA_MODEL")
        if primary_model:
            self.PRIMARY_MODEL = ModelConfig(name=primary_model)
        elif env_model:
            self.PRIMARY_MODEL = ModelConfig(name=env_model)
        if fallback_1:
            self.FALLBACK_1 = ModelConfig(name=fallback_1, timeout=90)
        if fallback_2:
            self.FALLBACK_2 = ModelConfig(name=fallback_2, timeout=90)
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session
    
    async def generate(
        self,
        model_name: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 5000,
        timeout: int = 60
    ) -> str:
        """
        Generate response from a specific model.
        """
        """
        Generate response from a specific model.
        """
        # Ensure we have a valid session
        session = await self._get_session()
        
        # Build request payload
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        
        # Add system prompt if provided
        if system_prompt:
            payload["system"] = system_prompt
        
        # Request JSON format
        payload["format"] = "json"
        
        try:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama returned {response.status}: {error_text}")
                
                result = await response.json()
                return result.get("response", "")
                
        except asyncio.TimeoutError:
            raise Exception(f"Timeout after {timeout}s for model {model_name}")
        except aiohttp.ClientError as e:
            raise Exception(f"Connection error for model {model_name}: {e}")
    
    async def generate_with_fallback(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Generate response with automatic fallback.
        
        Tries models in order:
        1. Primary (gpt-oss) - 2 retries
        2. Fallback 1 (llama3.1:70b) - 1 attempt
        3. Fallback 2 (mixtral) - 1 attempt
        4. Returns degraded response if all fail
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Returns:
            Tuple of (response_text, model_used)
        """
        models_to_try = [
            (self.PRIMARY_MODEL, 2),  # 2 retries
            (self.FALLBACK_1, 1),     # 1 attempt
            (self.FALLBACK_2, 1),     # 1 attempt
        ]
        
        last_error = None
        
        for model_config, max_attempts in models_to_try:
            for attempt in range(max_attempts):
                try:
                    print(f"[OllamaClient] Trying {model_config.name} (attempt {attempt + 1}/{max_attempts})")
                    
                    response = await self.generate(
                        model_name=model_config.name,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=model_config.temperature,
                        max_tokens=model_config.max_tokens,
                        timeout=model_config.timeout
                    )
                    
                    print(f"[OllamaClient] Success with {model_config.name}")
                    return response, model_config.name
                    
                except Exception as e:
                    last_error = e
                    print(f"[OllamaClient] Failed {model_config.name}: {e}")
                    
                    # Wait before retry (exponential backoff)
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(2 ** attempt)
        
        # All models failed
        print(f"[OllamaClient] All models failed, returning degraded response. Last error: {last_error}")
        return self.DEGRADED_RESPONSE, "degraded"
    
    async def health_check(self) -> dict:
        """
        Check Ollama server health and available models.
        
        Returns:
            Dict with health status and available models
        """
        session = await self._get_session()
        
        try:
            async with session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status != 200:
                    return {"status": "unhealthy", "error": f"HTTP {response.status}"}
                
                data = await response.json()
                models = [m.get("name") for m in data.get("models", [])]
                
                return {
                    "status": "healthy",
                    "models": models,
                    "primary_available": self.PRIMARY_MODEL.name in models,
                    "fallback1_available": self.FALLBACK_1.name in models,
                    "fallback2_available": self.FALLBACK_2.name in models
                }
                
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()


# Singleton instance
_ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """Get or create Ollama client singleton"""
    global _ollama_client
    
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    
    return _ollama_client

