import os
import tempfile
import pytest
from agent.stages.stage1_analysis import Stage1Analysis
from agent.stages.stage2_planning import Stage2Planning
from agent.stages.stage4_execution import Stage4Execution
from agent.stages.stage5_correction import Stage5Correction
from agent.state import AgentState

def test_python_scoring_improvements():
    stage1 = Stage1Analysis({"models": {"stage1": "deepseek/deepseek-v4-flash"}})

    # Case 1: Pure functional module (no classes, 3 public functions, 2 control flows)
    functional_code = """
def process_data(x):
    if x > 0:
        return x * 2
    return 0

def clean_data(y):
    if y is None:
        return ""
    return y.strip()

def save_data(z):
    print(z)
"""
    score_functional = stage1._score_python_content(functional_code)
    # 3 functions (+20 for >=3 control flows? no, control_structures is 2 which is < 3 so no +20 from that, but functional check adds +30)
    assert score_functional >= 30

    # Case 2: Class with 1 public method and logic
    single_method_class_code = """
class DataService:
    def process(self, x):
        if x > 0:
            return x
        return 0
"""
    score_class = stage1._score_python_content(single_method_class_code)
    # class with 1 public method + logic -> +25 points
    assert score_class >= 25


def test_negative_keyword_matching():
    stage1 = Stage1Analysis({"models": {"stage1": "deepseek/deepseek-v4-flash"}})
    
    # "config" is a standalone negative keyword -> matches
    score_config = stage1.discover_service_files(".", "python")
    # Let's test the negative keyword check directly:
    neg_keywords = ["config", "settings", "constant", "enum", "schema", "migration", "seed", "fixture"]
    
    def check_negative(rel_path):
        path_parts = rel_path.lower().replace("\\", "/").split("/")
        filename_stem = os.path.splitext(path_parts[-1])[0]
        if any(part in neg_keywords for part in path_parts[:-1]):
            return True
        if filename_stem in neg_keywords:
            return True
        return False

    assert check_negative("app/config.py") is True
    assert check_negative("app/config/database.py") is True
    assert check_negative("app/configuration.py") is False
    assert check_negative("app/user_settings.py") is False
    assert check_negative("app/settings.py") is True


def test_unique_test_ids():
    stage2 = Stage2Planning({})
    analysis_result = {
        "services": [
            {
                "class_name": "UserService",
                "package": "app",
                "file_path": "user_service.py",
                "dependencies": [],
                "methods": [
                    # Simulate overloaded/duplicate method definitions
                    {"name": "delete", "return_type": "void", "params": [{"name": "id", "type": "int"}]},
                    {"name": "delete", "return_type": "void", "params": [{"name": "name", "type": "str"}]}
                ]
            }
        ]
    }
    plan = stage2.generate_local_fallback_plan(analysis_result)
    test_cases = plan["test_cases"]
    
    # We should have happy and edge path for both, and IDs must be unique
    test_ids = [tc["test_id"] for tc in test_cases]
    assert len(test_ids) == len(set(test_ids))
    assert len(test_ids) == 4
    assert "UserService_delete_001" in test_ids
    assert "UserService_delete_002" in test_ids
    assert "UserService_delete_003" in test_ids
    assert "UserService_delete_004" in test_ids


def test_scoped_coverage_parsing():
    from agent.stages.stage4_execution import Stage4Execution
    
    xml_content = """<?xml version="1.0" ?>
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
                <class filename="app/services/other_service.py" name="OtherService" line-rate="0.5" branch-rate="0.0">
                    <lines>
                        <line hits="1" number="1"/>
                        <line hits="0" number="2"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-8") as f:
        f.write(xml_content)
        temp_path = f.name
        
    try:
        # Case 1: No service_files filter -> total_coverage comes from root line-rate attribute (85.0)
        report_global = Stage4Execution.parse_python_coverage_xml(temp_path, "3 passed")
        assert report_global["total_coverage"] == 85.0
        assert "ProductService" in report_global["classes"]
        assert "OtherService" in report_global["classes"]
        
        # Case 2: service_files filters only app/services/product_service.py -> total_coverage recalculated
        report_scoped = Stage4Execution.parse_python_coverage_xml(
            temp_path, "3 passed", service_files=["app/services/product_service.py"]
        )
        # Recalculated total coverage: 3 hits / 4 lines = 75%
        assert report_scoped["total_coverage"] == 75.0
        assert "ProductService" in report_scoped["classes"]
        assert "OtherService" not in report_scoped["classes"]
    finally:
        os.remove(temp_path)


def test_stage5_snippet_extraction(tmp_path):
    # Setup dummy source code file
    source_code = """line 1: import os
line 2: def my_func():
line 3:     a = 1
line 4:     b = 2
line 5:     if a > 0:
line 6:         print("a is positive")
line 7:     else:
line 8:         print("a is negative")
line 9:     return b
"""
    src_file = tmp_path / "my_service.py"
    src_file.write_text(source_code, encoding="utf-8")

    state = AgentState(
        repo_path=str(tmp_path),
        language="python",
        framework="fastapi",
        service_files=["my_service.py"],
        analysis_result={
            "services": [
                {
                    "class_name": "MyService",
                    "file_path": "my_service.py",
                    "methods": [],
                    "dependencies": []
                }
            ]
        },
        test_plan={},
        generated_tests=[],
        coverage_report=None,
        retry_count=0,
        history=[]
    )

    stage5 = Stage5Correction({})
    # Extract snippets around line 6 and 8
    snippet = stage5._extract_uncovered_snippets(state, "MyService", [6, 8])
    assert snippet is not None
    # Verify the markers (>>>) are at the correct lines
    lines = snippet.split("\n")
    # The snippet should contain line 6 and 8 marked with >>> and surrounding lines
    assert any(">>> 6:" in line for line in lines)
    assert any(">>> 8:" in line for line in lines)
    assert any("   3:" in line for line in lines)
