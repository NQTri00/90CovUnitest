import pytest
from agent.stages.stage5_correction import Stage5Correction
from agent.state import AgentState

def test_stage5_coverage_met():
    stage5 = Stage5Correction({"max_retry": 3})
    
    state = AgentState(
        repo_path="/fake",
        language="python",
        framework="fastapi",
        service_files=[],
        analysis_result={},
        test_plan={
            "plan_version": "1.0",
            "target_coverage": 90,
            "test_cases": []
        },
        generated_tests=[],
        coverage_report={
            "total_coverage": 92.5,
            "summary": {"total_tests": 1, "passed": 1, "failed": 0, "skipped": 0},
            "classes": {},
            "failures": []
        },
        retry_count=0,
        history=[]
    )
    
    final_state = stage5.run(state)
    assert final_state["retry_count"] == 0 # unchanged
    assert "Target coverage achieved" in final_state["history"][-1]

def test_stage5_max_retry_reached():
    stage5 = Stage5Correction({"max_retry": 3})
    
    state = AgentState(
        repo_path="/fake",
        language="python",
        framework="fastapi",
        service_files=[],
        analysis_result={},
        test_plan={
            "plan_version": "1.0",
            "target_coverage": 90,
            "test_cases": []
        },
        generated_tests=[],
        coverage_report={
            "total_coverage": 75.0, # under target
            "summary": {"total_tests": 1, "passed": 1, "failed": 0, "skipped": 0},
            "classes": {},
            "failures": []
        },
        retry_count=3, # max retry reached
        history=[]
    )
    
    final_state = stage5.run(state)
    assert final_state["retry_count"] == 3 # unchanged
    assert "Max retry limit reached" in final_state["history"][-1]

def test_stage5_trigger_correction_loop():
    stage5 = Stage5Correction({"max_retry": 3})
    
    initial_plan = {
        "plan_version": "1.0",
        "target_coverage": 90,
        "test_cases": [
            {
                "service": "ProductService",
                "method": "getName",
                "test_id": "ProductService_getName_001",
                "type": "happy_path",
                "description": "desc",
                "setup": {"mocks": []},
                "input": {},
                "expected": {"return_type": "String", "assertions": []}
            }
        ]
    }
    
    state = AgentState(
        repo_path="/fake",
        language="python",
        framework="fastapi",
        service_files=[],
        analysis_result={},
        test_plan=initial_plan,
        generated_tests=[],
        coverage_report={
            "total_coverage": 75.0, # under target
            "summary": {"total_tests": 1, "passed": 1, "failed": 0, "skipped": 0},
            "classes": {"ProductService": {"line_coverage": 75.0, "uncovered_lines": [10, 15]}},
            "failures": []
        },
        retry_count=0,
        history=[]
    )
    
    import unittest.mock
    import json
    
    stage5.llm_client.api_key = "sk-or-v1-dummy-real-key"
    mocked_plan = {
        "plan_version": "1.0",
        "target_coverage": 90,
        "test_cases": [
            {
                "service": "ProductService",
                "method": "getName",
                "test_id": "ProductService_getName_001",
                "type": "happy_path",
                "description": "desc",
                "setup": {"mocks": []},
                "input": {},
                "expected": {"return_type": "String", "assertions": []}
            },
            {
                "service": "SimulatedService",
                "method": "simulatedMethod",
                "test_id": "SimulatedService_simulatedMethod_999",
                "type": "happy_path",
                "description": "Simulated test case added during feedback loop to cover lines 10 and 15",
                "setup": {"mocks": []},
                "input": {},
                "expected": {"return_type": "void", "assertions": ["result == null"]}
            }
        ]
    }
    
    with unittest.mock.patch.object(stage5.llm_client, "chat_completion", return_value=json.dumps(mocked_plan)):
        final_state = stage5.run(state)
        
    assert final_state["retry_count"] == 1 # incremented
    assert "Self-correction loop retry #1 triggered." in final_state["history"][-1]
    
    updated_plan = final_state["test_plan"]
    assert len(updated_plan["test_cases"]) == 2 # 1 original + 1 enriched
    assert updated_plan["test_cases"][-1]["test_id"] == "SimulatedService_simulatedMethod_999"
