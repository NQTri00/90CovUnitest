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

def test_main_cli_execution(temp_repo):
    # Verify end-to-end run via CLI
    cmd = [".\\venv\\Scripts\\python", "main.py", "--repo", temp_repo]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, encoding="utf-8")
    
    assert result.returncode == 0
    assert "NHẬT KÝ HOẠT ĐỘNG" in result.stdout
    assert "KẾT QUẢ CUỐI CÙNG" in result.stdout
    assert "Saved test plan to" in result.stdout
    assert "Saved coverage report to" in result.stdout
    
    # Check physical output files
    assert os.path.exists(os.path.join(temp_repo, "test_plan.json"))
    assert os.path.exists(os.path.join(temp_repo, "coverage_report.json"))
    assert os.path.exists(os.path.join(temp_repo, "generated_tests", "app", "services", "test_simple_service.py"))
