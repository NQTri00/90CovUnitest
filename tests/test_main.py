import os
import shutil
import tempfile
import subprocess
import pytest

MOCK_SERVICE = """
class SimpleService:
    def greet(self, name: str) -> str:
        return f"Hello {name}"
"""

@pytest.fixture
def temp_repo():
    temp_dir = tempfile.mkdtemp()
    
    # Write python service file
    service_path = os.path.join(temp_dir, "app", "services", "simple_service.py")
    os.makedirs(os.path.dirname(service_path), exist_ok=True)
    with open(service_path, "w", encoding="utf-8") as f:
        f.write(MOCK_SERVICE)
        
    with open(os.path.join(temp_dir, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("pytest\n")
        
    yield temp_dir
    shutil.rmtree(temp_dir)

def test_main_cli_help():
    # Verify help menu works
    cmd = [".\\venv\\Scripts\\python", "main.py", "--help"]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, encoding="utf-8")
    assert result.returncode == 0
    assert "Unit Test Agent" in result.stdout

def test_main_cli_execution(temp_repo, capsys):
    import io
    import sys
    import unittest.mock
    from agent.stages.stage4_execution import Stage4Execution
    from agent.stages.stage5_correction import Stage5Correction
    from main import main

    def mock_stage4_run(self, state):
        state["coverage_report"] = {
            "total_coverage": 95.0,
            "summary": {"total_tests": 1, "passed": 1, "failed": 0, "skipped": 0},
            "classes": {
                "SimpleService": {
                    "line_coverage": 95.0,
                    "branch_coverage": 95.0,
                    "uncovered_lines": []
                }
            },
            "failures": []
        }
        state["history"].append("Stage 4 completed: Test execution and coverage analysis done.")
        return state

    def mock_stage5_run(self, state):
        state["history"].append("Self-correction loop finished: Target coverage achieved.")
        return state

    sys_argv_backup = sys.argv
    sys.argv = ["main.py", "--repo", temp_repo]
    
    with unittest.mock.patch.object(Stage4Execution, "run", mock_stage4_run), \
         unittest.mock.patch.object(Stage5Correction, "run", mock_stage5_run):
        main()
        
    sys.argv = sys_argv_backup
    
    captured = capsys.readouterr()
    output = captured.out
    
    assert "NHẬT KÝ HOẠT ĐỘNG" in output
    assert "KẾT QUẢ CUỐI CÙNG" in output
    assert "Saved test plan to" in output
    assert "Saved coverage report to" in output
    
    # Check physical output files
    assert os.path.exists(os.path.join(temp_repo, "test_plan.json"))
    assert os.path.exists(os.path.join(temp_repo, "coverage_report.json"))
    assert os.path.exists(os.path.join(temp_repo, "generated_tests", "app", "services", "test_simple_service.py"))
