import os
import pytest
from agent.stages.stage2_planning import Stage2Planning
from agent.state import AgentState

MOCK_ANALYSIS_RESULT = {
    "repo": {
        "path": "/fake/project",
        "language": "java",
        "framework": "spring-boot",
        "version": "3.2.0",
        "build_tool": "maven"
    },
    "services": [
        {
            "class_name": "UserService",
            "package": "com.example.demo.service",
            "file_path": "src/main/java/com/example/demo/service/UserService.java",
            "annotations": ["@Service"],
            "methods": [
                {
                    "name": "getUserById",
                    "visibility": "public",
                    "params": [
                        { "name": "id", "type": "Long" }
                    ],
                    "return_type": "User",
                    "throws": ["UserNotFoundException"],
                    "annotations": [],
                    "complexity": 3,
                    "priority": "HIGH"
                }
            ],
            "dependencies": [
                {
                    "field_name": "userRepository",
                    "type": "UserRepository",
                    "category": "repository",
                    "mock_strategy": "MockBean",
                    "annotations": ["@Autowired"]
                }
            ]
        }
    ]
}

def test_stage2_planning():
    config = {
        "models": {
            "stage2": "deepseek/deepseek-v4-flash"
        }
    }
    
    # Run in local fallback mode by ensuring OPENROUTER_API_KEY is unset or mock
    os.environ["OPENROUTER_API_KEY"] = "your-openrouter-api-key-here"
    
    stage2 = Stage2Planning(config)
    
    initial_state = AgentState(
        repo_path="/fake/project",
        language="java",
        framework="spring-boot",
        service_files=["src/main/java/com/example/demo/service/UserService.java"],
        analysis_result=MOCK_ANALYSIS_RESULT,
        test_plan=None,
        generated_tests=[],
        coverage_report=None,
        retry_count=0,
        history=[]
    )
    
    final_state = stage2.run(initial_state)
    
    test_plan = final_state["test_plan"]
    assert test_plan is not None
    assert test_plan["plan_version"] == "1.0"
    assert test_plan["target_coverage"] == 90
    
    test_cases = test_plan["test_cases"]
    # We expect 3 test cases: happy_path (001), edge_case (002), error_path (003)
    assert len(test_cases) == 3
    
    # Validate test IDs
    ids = [tc["test_id"] for tc in test_cases]
    assert "UserService_getUserById_001" in ids
    assert "UserService_getUserById_002" in ids
    assert "UserService_getUserById_003" in ids
    
    # Validate structure of happy path test case
    happy_case = next(tc for tc in test_cases if tc["type"] == "happy_path")
    assert happy_case["service"] == "UserService"
    assert happy_case["method"] == "getUserById"
    assert len(happy_case["setup"]["mocks"]) == 1
    assert happy_case["setup"]["mocks"][0]["dependency"] == "userRepository"
    assert happy_case["setup"]["mocks"][0]["method"] == "findById"
    assert happy_case["setup"]["mocks"][0]["behavior"] == "return"
    assert happy_case["input"]["id"] == "1L"
    assert happy_case["expected"]["return_type"] == "User"
    
    # Validate structure of error path test case
    error_case = next(tc for tc in test_cases if tc["type"] == "error_path")
    assert error_case["expected"]["throws"] == "UserNotFoundException"
    assert error_case["setup"]["mocks"][0]["behavior"] == "throw"
    assert error_case["setup"]["mocks"][0]["return_value"] == "UserNotFoundException"
