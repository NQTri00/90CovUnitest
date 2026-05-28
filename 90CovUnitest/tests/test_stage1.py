import os
import shutil
import tempfile
import pytest
from agent.stages.stage1_analysis import Stage1Analysis
from agent.state import AgentState

MOCK_SPRING_BOOT_PROJECT = {
    "pom.xml": """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
</project>
""",
    "src/main/java/com/example/demo/service/ProductService.java": """
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String getProductName(Long id) {
        if (id == 1L) {
            return "Laptop";
        }
        return "Unknown";
    }
}
"""
}

@pytest.fixture
def temp_project_dir():
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    
    # Write mock files
    for rel_path, content in MOCK_SPRING_BOOT_PROJECT.items():
        abs_path = os.path.join(temp_dir, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    yield temp_dir
    
    # Cleanup
    shutil.rmtree(temp_dir)

def test_stage1_analysis(temp_project_dir):
    config = {
        "models": {
            "stage1": "kimi/kimi-k2.6"
        }
    }
    
    # Ensure OPENROUTER_API_KEY is not defined to trigger local AST fallback
    # which is ideal for offline unit testing
    os.environ["OPENROUTER_API_KEY"] = "your-openrouter-api-key-here"

    stage1 = Stage1Analysis(config)
    
    initial_state = AgentState(
        repo_path=temp_project_dir,
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
    
    final_state = stage1.run(initial_state)
    
    assert final_state["language"] == "java"
    assert final_state["framework"] == "spring-boot"
    assert len(final_state["service_files"]) == 1
    assert "ProductService.java" in final_state["service_files"][0]
    
    analysis_result = final_state["analysis_result"]
    assert analysis_result is not None
    assert analysis_result["repo"]["language"] == "java"
    assert analysis_result["repo"]["framework"] == "spring-boot"
    assert analysis_result["repo"]["build_tool"] == "maven"
    
    services = analysis_result["services"]
    assert len(services) == 1
    assert services[0]["class_name"] == "ProductService"
    assert len(services[0]["methods"]) == 1
    assert services[0]["methods"][0]["name"] == "getProductName"
    assert services[0]["methods"][0]["complexity"] == 2  # 1 base + 1 if

def test_discover_service_files_heuristics():
    config = {}
    stage1 = Stage1Analysis(config)
    
    # Create temp dir structure with various files
    temp_dir = tempfile.mkdtemp()
    try:
        # 1. ProductService.java -> service keyword, public methods, annotations -> High score
        service_java = os.path.join(temp_dir, "src/main/java/com/example/demo/service/ProductService.java")
        os.makedirs(os.path.dirname(service_java), exist_ok=True)
        with open(service_java, "w", encoding="utf-8") as f:
            f.write("""
            package com.example.demo.service;
            import org.springframework.stereotype.Service;
            @Service
            public class ProductService {
                public void doSomething() {}
                public void doAnother() {}
            }
            """)
            
        # 2. CalculatorHandler.py -> handler keyword, 1 class, 2 public methods -> High score
        handler_py = os.path.join(temp_dir, "app/handlers/calculator.py")
        os.makedirs(os.path.dirname(handler_py), exist_ok=True)
        with open(handler_py, "w", encoding="utf-8") as f:
            f.write("""
class CalculatorHandler:
    def __init__(self, dependency):
        self.dep = dependency
    def add(self, a, b):
        return a + b
    def subtract(self, a, b):
        return a - b
            """)
            
        # 3. config.py -> config keyword (-50), no class and <50 lines (-30) -> Negative score
        config_py = os.path.join(temp_dir, "config/config.py")
        os.makedirs(os.path.dirname(config_py), exist_ok=True)
        with open(config_py, "w", encoding="utf-8") as f:
            f.write("DATABASE_URL = 'sqlite://'\nDEBUG = True\n")
            
        # 4. test_service.py -> Starts with test_ -> Hard Exclude
        test_py = os.path.join(temp_dir, "app/test_service.py")
        os.makedirs(os.path.dirname(test_py), exist_ok=True)
        with open(test_py, "w", encoding="utf-8") as f:
            f.write("def test_something(): pass\n")
            
        # 5. venv directory -> Hard Exclude
        venv_py = os.path.join(temp_dir, "venv/lib/python3.11/site-packages/some_service.py")
        os.makedirs(os.path.dirname(venv_py), exist_ok=True)
        with open(venv_py, "w", encoding="utf-8") as f:
            f.write("class SomeService: pass\n")

        # Test Java discovery
        java_discovered = stage1.discover_service_files(temp_dir, "java")
        # Only ProductService.java should be discovered
        assert len(java_discovered) == 1
        assert "ProductService.java" in java_discovered[0].replace("\\", "/")
        
        # Test Python discovery
        python_discovered = stage1.discover_service_files(temp_dir, "python")
        # Only CalculatorHandler.py should be discovered
        assert len(python_discovered) == 1
        assert "calculator.py" in python_discovered[0].replace("\\", "/")
        
    finally:
        shutil.rmtree(temp_dir)
