import os
import tempfile
import pytest
from jsonschema import validate
from agent.stages.stage4_execution import Stage4Execution
from agent.state import AgentState

MOCK_PYTHON_COV_XML = """<?xml version="1.0" ?>
<coverage branch-rate="0.75" line-rate="0.85" timestamp="123456" version="7.0">
    <packages>
        <package name="app.services">
            <classes>
                <class filename="app/services/product_service.py" name="ProductService" line-rate="0.8" branch-rate="0.5">
                    <lines>
                        <line hits="1" number="1"/>
                        <line hits="1" number="2"/>
                        <line hits="0" number="3"/>
                        <line hits="1" number="4"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""

MOCK_JACOCO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<report name="demo">
    <package name="com/example/demo/service">
        <sourcefile name="ProductService.java">
            <line nr="1" mi="0" ci="2" mb="0" cb="0"/>
            <line nr="2" mi="1" ci="0" mb="0" cb="0"/>
            <line nr="3" mi="0" ci="1" mb="0" cb="0"/>
            <counter type="LINE" missed="1" covered="2"/>
            <counter type="BRANCH" missed="0" covered="0"/>
        </sourcefile>
    </package>
</report>
"""

def test_parse_python_coverage_xml():
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-8") as f:
        f.write(MOCK_PYTHON_COV_XML)
        temp_path = f.name
        
    try:
        report = Stage4Execution.parse_python_coverage_xml(temp_path, "3 passed")
        
        assert report["total_coverage"] == 85.0
        assert report["summary"]["passed"] == 3
        assert report["summary"]["total_tests"] == 3
        
        classes = report["classes"]
        assert "ProductService" in classes
        assert classes["ProductService"]["line_coverage"] == 75.0 # 3 covered / 4 lines
        assert classes["ProductService"]["branch_coverage"] == 50.0
        assert classes["ProductService"]["uncovered_lines"] == [3]
    finally:
        os.remove(temp_path)

def test_parse_jacoco_xml():
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-8") as f:
        f.write(MOCK_JACOCO_XML)
        temp_path = f.name
        
    try:
        report = Stage4Execution.parse_jacoco_xml(temp_path, passed=2, failed=1, failures_list=[])
        
        assert report["total_coverage"] == 66.67 # 2 covered / 3 total
        assert report["summary"]["passed"] == 2
        assert report["summary"]["failed"] == 1
        
        classes = report["classes"]
        assert "ProductService" in classes
        assert classes["ProductService"]["line_coverage"] == 66.67
        assert classes["ProductService"]["uncovered_lines"] == [2]
    finally:
        os.remove(temp_path)

def test_mock_coverage_report_schema_validation():
    # Setup dummy agent state
    state = AgentState(
        repo_path="/fake",
        language="python",
        framework="fastapi",
        service_files=["app/services/product_service.py"],
        analysis_result={
            "services": [
                {
                    "class_name": "ProductService",
                    "package": "",
                    "file_path": "app/services/product_service.py",
                    "methods": [{"name": "get_product_name", "return_type": "str", "params": []}],
                    "dependencies": []
                }
            ]
        },
        test_plan={
            "plan_version": "1.0",
            "target_coverage": 90,
            "test_cases": [
                {
                    "service": "ProductService",
                    "method": "get_product_name",
                    "test_id": "ProductService_get_product_name_001",
                    "type": "happy_path",
                    "description": "desc",
                    "setup": {"mocks": []},
                    "input": {},
                    "expected": {"return_type": "str", "assertions": []}
                }
            ]
        },
        generated_tests=[],
        coverage_report=None,
        retry_count=0,
        history=[]
    )
    
    stage4 = Stage4Execution({})
    final_state = stage4.run(state)
    
    report = final_state["coverage_report"]
    assert report is not None
    
    # Validate report output against coverage_report.schema.json
    schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schemas", "coverage_report.schema.json")
    import json
    with open(schema_path, "r", encoding="utf-8") as sf:
        schema = json.load(sf)
        
    validate(instance=report, schema=schema) # should pass without throwing ValidationError
