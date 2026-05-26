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
