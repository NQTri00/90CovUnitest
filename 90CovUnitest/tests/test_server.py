import os
import pytest
from fastapi.testclient import TestClient
from server import app, runs_db

client = TestClient(app)

def test_read_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "UNIT TEST AGENT" in response.text

def test_get_runs_empty():
    runs_db.clear()
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert response.json() == []

def test_run_agent_invalid_path():
    response = client.post("/api/run", json={"repo_path": "non_existent_folder_abc_123"})
    assert response.status_code == 400
    assert "không tồn tại" in response.json()["detail"]

def test_run_agent_valid_path_and_status():
    runs_db.clear()
    # Use demo_project as it exists
    response = client.post("/api/run", json={"repo_path": "demo_project"})
    assert response.status_code == 200
    
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "running"
    
    run_id = data["run_id"]
    assert run_id in runs_db
    
    # Query status
    status_response = client.get(f"/api/status/{run_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["run_id"] == run_id
    assert status_data["repo_path"] == "demo_project"

def test_get_status_not_found():
    response = client.get("/api/status/invalid-uuid-12345")
    assert response.status_code == 404
    assert response.json()["detail"] == "Run ID not found"
