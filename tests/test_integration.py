import pytest
from fastapi.testclient import TestClient
from src.api.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data
    assert "timestamp" in data

def test_analyze_flow(client):
    # 1. Get example bundle
    response = client.get("/ai/example-bundle")
    assert response.status_code == 200
    bundle = response.json()
    
    # 2. Analyze the bundle
    # We use no-rag or simple endpoint to avoid external dependencies if possible, 
    # but let's try the main one first as it's the core value.
    # However, for a quick test, we might want to mock things or use the no-rag endpoint 
    # if we don't want to rely on Pinecone/Ollama being perfectly ready in the test environment.
    # Given the user has the app running and wants to "run", let's try the full flow 
    # but maybe fallback to no-rag if we want to be safe. 
    # Let's test the /ai/analyze/no-rag endpoint to be deterministic and fast for this first test.
    
    payload = {
        "bundle": bundle,
        "use_rag": False,
        "top_k": 5
    }
    
    # Using the main endpoint but with use_rag=False (if supported by payload) 
    # or just hitting the no-rag endpoint directly.
    # The main endpoint takes AnalyzeRequest which has use_rag.
    
    response = client.post("/ai/analyze", json=payload)
    
    # If the main endpoint fails due to missing services (like Pinecone), 
    # we might get a 500. But we set use_rag=False.
    # Let's check the code for analyze_correlation_bundle in main.py
    # It calls service.create_ai_recommendation.
    
    assert response.status_code == 200
    data = response.json()
    
    assert "recommendation" in data
    rec = data["recommendation"]
    assert "rootCause" in rec
    assert "recommendedAction" in rec
    assert "aiConfidence" in rec
