"""
Groq Client for High-Performance Inference
Mirrors OllamaClient interface for easy swapping.
"""

import os
import aiohttp
import json
from typing import Optional, Tuple
from dataclasses import dataclass

@dataclass
class ModelConfig:
    """Configuration for a model"""
    name: str
    temperature: float = 0.3
    max_tokens: int = 5000

class GroqClient:
    """
    Client for Groq API (OpenAI-compatible).
    """
    
    PRIMARY_MODEL = ModelConfig(name="llama-3.3-70b-versatile")
    FALLBACK_MODEL = ModelConfig(name="llama-3.1-70b-versatile")
    
    DEGRADED_RESPONSE = """{
  "root_cause_analysis": {
    "summary": "AI Analysis Failed",
    "primary_cause": "unknown",
    "impact": "unknown"
  },
  "recommendations": [],
  "confidence_assessment": {
    "final_confidence": 0.0,
    "action": "manual_review"
  },
  "requires_human_review": true,
  "auto_heal_candidate": false
}"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        
        if not self.api_key:
            print("[GroqClient] Warning: GROQ_API_KEY not set. API calls will fail.")
            
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def generate(
        self,
        model_name: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 5000
    ) -> str:
        """
        Generate response using Groq API.
        """
        session = await self._get_session()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}
        }
        
        try:
            async with session.post(self.base_url, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"Groq API Error {response.status}: {text}")
                
                data = await response.json()
                content = data['choices'][0]['message']['content']
                return content
                
        except Exception as e:
            raise Exception(f"Groq Request Failed: {e}")

    async def generate_with_fallback(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Try Primary (Llama3-70b), then Fallback (Mixtral).
        """
        models = [self.PRIMARY_MODEL, self.FALLBACK_MODEL]
        
        for model in models:
            try:
                print(f"[GroqClient] Trying {model.name}...")
                response = await self.generate(
                    model_name=model.name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=model.temperature,
                    max_tokens=model.max_tokens
                )
                print(f"[GroqClient] Success with {model.name}")
                return response, model.name
            except Exception as e:
                print(f"[GroqClient] Failed {model.name}: {e}")
        
        print("[GroqClient] All models failed.")
        return self.DEGRADED_RESPONSE, "degraded"

    async def health_check(self) -> dict:
        """Simple health check by listing models"""
        if not self.api_key:
             return {"status": "unhealthy", "error": "Missing API Key"}
             
        session = await self._get_session()
        try:
            async with session.get("https://api.groq.com/openai/v1/models") as response:
                if response.status == 200:
                    return {"status": "healthy", "provider": "groq"}
                else:
                    return {"status": "unhealthy", "error": f"HTTP {response.status}"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

# Singleton instance
_groq_client: Optional[GroqClient] = None

def get_groq_client() -> GroqClient:
    """Get or create Groq client singleton"""
    global _groq_client
    
    if _groq_client is None:
        _groq_client = GroqClient()
    
    return _groq_client
