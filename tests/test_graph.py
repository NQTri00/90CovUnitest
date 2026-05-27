import os
import shutil
import tempfile
import pytest
from agent.graph import build_agent_graph
from agent.state import AgentState

MOCK_PYTHON_SERVICE = """
class UserService:
    def get_user(self, user_id: int) -> str:
        if user_id == 1:
            return "Alice"
        return "Bob"
"""

@pytest.fixture
def temp_project():
    temp_dir = tempfile.mkdtemp()
    
    # Write python service file
    service_path = os.path.join(temp_dir, "app", "services", "user_service.py")
    os.makedirs(os.path.dirname(service_path), exist_ok=True)
    with open(service_path, "w", encoding="utf-8") as f:
        f.write(MOCK_PYTHON_SERVICE)
        
    # Write setup/pyproject file to trigger Python detection
    with open(os.path.join(temp_dir, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("pytest\n")
        
    yield temp_dir
    shutil.rmtree(temp_dir)

def test_full_agent_graph_execution(temp_project):
    config = {
        "models": {
            "stage1": "kimi/kimi-k2.6",
            "stage2": "deepseek/deepseek-v4-flash",
            "stage3": "kimi/kimi-k2.6",
            "stage5": "kimi/kimi-k2.6"
        },
        "max_retry": 3
    }
    
    # Offline run
    os.environ["OPENROUTER_API_KEY"] = "your-openrouter-api-key-here"
    
    import unittest.mock
    import json
    from agent.stages.stage4_execution import Stage4Execution
    from agent.stages.stage5_correction import Stage5Correction
    
    def mock_stage4_run(self, state):
        retry_count = state.get("retry_count", 0)
        total_coverage = 75.0 if retry_count == 0 else 95.0
        state["coverage_report"] = {
            "total_coverage": total_coverage,
            "summary": {"total_tests": 1, "passed": 1, "failed": 0, "skipped": 0},
            "classes": {
                "UserService": {
                    "line_coverage": total_coverage,
                    "branch_coverage": total_coverage,
                    "uncovered_lines": [10, 15] if retry_count == 0 else []
                }
            },
            "failures": []
        }
        state["history"].append("Stage 4 completed: Test execution and coverage analysis done.")
        return state

    def mock_stage5_run(self, state):
        coverage_report = state.get("coverage_report")
        test_plan = state.get("test_plan")
        current_coverage = coverage_report.get("total_coverage", 0.0)
        target_coverage = float(test_plan.get("target_coverage", 90.0))
        retry_count = state.get("retry_count", 0)
        if current_coverage >= target_coverage:
            state["history"].append("Self-correction loop finished: Target coverage achieved.")
            return state
        new_retry_count = retry_count + 1
        state["retry_count"] = new_retry_count
        
        corrected_plan = json.loads(json.dumps(test_plan))
        corrected_plan["test_cases"].append({
            "service": "UserService",
            "method": "get_user",
            "test_id": "SimulatedService_simulatedMethod_999",
            "type": "happy_path",
            "description": "Simulated test case",
            "setup": {"mocks": []},
            "input": {},
            "expected": {"return_type": "void", "assertions": []}
        })
        state["test_plan"] = corrected_plan
        state["history"].append(f"Self-correction loop retry #{new_retry_count} triggered.")
        return state

    initial_state = AgentState(
        repo_path=temp_project,
        language="",
        framework="",
        service_files=[],
        analysis_result=None,
        test_plan=None,
        generated_tests=[],
        coverage_report=None,
        retry_count=0,
        history=[]
    )

    with unittest.mock.patch.object(Stage4Execution, "run", mock_stage4_run), \
         unittest.mock.patch.object(Stage5Correction, "run", mock_stage5_run):
        app = build_agent_graph(config)
        final_state = app.invoke(initial_state)
    
    # Assertions
    assert final_state["language"] == "python"
    assert final_state["framework"] == "fastapi"
    assert len(final_state["service_files"]) == 1
    assert "user_service.py" in final_state["service_files"][0]
    
    assert final_state["test_plan"] is not None
    assert len(final_state["generated_tests"]) == 1
    assert "test_user_service.py" in final_state["generated_tests"][0]["file_path"]
    
    # Assert loop ran and terminated successfully
    # First execution coverage simulated at 75% -> triggers correction loop
    # Second execution coverage simulated at 95% -> terminates loop
    assert final_state["retry_count"] == 1
    assert final_state["coverage_report"]["total_coverage"] == 95.0
    
    # Verify file physically exists on disk inside temp_project
    test_abs_path = os.path.join(temp_project, "generated_tests", "app", "services", "test_user_service.py")
    assert os.path.exists(test_abs_path)
    
    # Verify history logs the execution stages
    history = final_state["history"]
    assert any("Stage 1 completed" in log for log in history)
    assert any("Stage 2 completed" in log for log in history)
    assert any("Stage 3 completed" in log for log in history)
    assert any("Stage 4 completed" in log for log in history)
    assert any("Self-correction loop retry #1 triggered" in log for log in history)
    assert any("Self-correction loop finished: Target coverage achieved" in log for log in history)
