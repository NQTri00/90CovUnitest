import os
import pytest
import shutil
import tempfile
from server import runs_db, run_agent_task, resume_agent_task

MOCK_PYTHON_SERVICE = """
class SimpleService:
    def process_data(self, value: int) -> int:
        if value < 0:
            return 0
        return value * 2
"""

@pytest.fixture
def temp_project():
    temp_dir = tempfile.mkdtemp()
    
    # Write python service file
    service_path = os.path.join(temp_dir, "app", "services", "simple_service.py")
    os.makedirs(os.path.dirname(service_path), exist_ok=True)
    with open(service_path, "w", encoding="utf-8") as f:
        f.write(MOCK_PYTHON_SERVICE)
        
    # Write setup/pyproject file to trigger Python detection
    with open(os.path.join(temp_dir, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("pytest\n")
        
    yield temp_dir
    shutil.rmtree(temp_dir)

def test_hitl_pause_resume_pipeline(temp_project):
    # Set mock API Key to enforce offline/fallback mode
    os.environ["OPENROUTER_API_KEY"] = "your-openrouter-api-key-here"

    run_id = "test-hitl-run-123"
    runs_db[run_id] = {
        "run_id": run_id,
        "repo_path": temp_project,
        "status": "running",
        "logs": [],
        "progress": None,
        "error": None
    }

    # 1. Run Phase 1 (Stage 1 & 2)
    print("Running Phase 1...")
    run_agent_task(run_id, temp_project)

    # Assert pause status and data structures
    assert runs_db[run_id]["status"] == "awaiting_user_approval"
    assert runs_db[run_id]["progress"]["stage"] == 2
    assert runs_db[run_id]["progress"]["percentage"] == 100
    
    test_plan = runs_db[run_id]["test_plan"]
    assert test_plan is not None
    assert len(test_plan["test_cases"]) > 0

    # Extract all selected test cases
    selected_test_ids = [tc["test_id"] for tc in test_plan["test_cases"]]
    assert len(selected_test_ids) > 0
    print(f"Phase 1 complete. Test plan generated with {len(selected_test_ids)} cases.")

    # 2. Run Phase 2 (Stage 3, 4, 5) with filter list
    print("Running Phase 2 (Resuming)...")
    resume_agent_task(run_id, selected_test_ids)

    # Assert successful completion
    assert runs_db[run_id]["status"] == "completed"
    assert runs_db[run_id]["progress"]["stage"] == 5
    assert runs_db[run_id]["progress"]["percentage"] == 100
    assert runs_db[run_id]["coverage_report"] is not None
    assert "generated_files" in runs_db[run_id]

    print(f"Phase 2 complete. Generated {len(runs_db[run_id]['generated_files'])} test files.")
