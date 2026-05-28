import os
import shutil
import tempfile
import pytest
import py_compile
import javalang
from agent.stages.stage3_generation import Stage3Generation
from agent.state import AgentState

MOCK_PROJECT_FILES = {
    "src/main/java/com/example/demo/service/ProductService.java": """
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String getProductName(Long id) {
        return "Laptop";
    }
}
""",
    "app/services/product_service.py": """
class ProductService:
    def get_product_name(self, product_id: int) -> str:
        return "Laptop"
"""
}

MOCK_TEST_PLAN_JAVA = {
    "plan_version": "1.0",
    "target_coverage": 90,
    "test_cases": [
        {
            "service": "ProductService",
            "method": "getProductName",
            "test_id": "ProductService_getProductName_001",
            "type": "happy_path",
            "description": "Gọi thành công ProductService.getProductName",
            "setup": {
                "mocks": []
            },
            "input": {
                "id": "1L"
            },
            "expected": {
                "return_type": "String",
                "assertions": [
                    'result.equals("Laptop")'
                ]
            }
        }
    ]
}

MOCK_TEST_PLAN_PYTHON = {
    "plan_version": "1.0",
    "target_coverage": 90,
    "test_cases": [
        {
            "service": "ProductService",
            "method": "get_product_name",
            "test_id": "ProductService_get_product_name_001",
            "type": "happy_path",
            "description": "Gọi thành công get_product_name",
            "setup": {
                "mocks": []
            },
            "input": {
                "product_id": "1"
            },
            "expected": {
                "return_type": "str",
                "assertions": [
                    "result == 'Laptop'"
                ]
            }
        }
    ]
}

@pytest.fixture
def mock_repo_dir():
    temp_dir = tempfile.mkdtemp()
    for rel_path, content in MOCK_PROJECT_FILES.items():
        abs_path = os.path.join(temp_dir, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
    yield temp_dir
    shutil.rmtree(temp_dir)

def test_stage3_generation_java(mock_repo_dir):
    config = {"models": {"stage3": "kimi/kimi-k2.6"}}
    os.environ["OPENROUTER_API_KEY"] = "your-openrouter-api-key-here"
    
    stage3 = Stage3Generation(config)
    
    initial_state = AgentState(
        repo_path=mock_repo_dir,
        language="java",
        framework="spring-boot",
        service_files=["src/main/java/com/example/demo/service/ProductService.java"],
        analysis_result={
            "services": [
                {
                    "class_name": "ProductService",
                    "package": "com.example.demo.service",
                    "file_path": "src/main/java/com/example/demo/service/ProductService.java",
                    "methods": [{"name": "getProductName", "return_type": "String", "params": [{"name": "id", "type": "Long"}]}],
                    "dependencies": []
                }
            ]
        },
        test_plan=MOCK_TEST_PLAN_JAVA,
        generated_tests=[],
        coverage_report=None,
        retry_count=0,
        history=[]
    )
    
    final_state = stage3.run(initial_state)
    
    generated = final_state["generated_tests"]
    assert len(generated) == 1
    assert generated[0]["service"] == "ProductService"
    assert "ProductServiceTest.java" in generated[0]["file_path"]
    
    # Assert physical file exists and compiles under javalang
    test_abs_path = os.path.join(mock_repo_dir, generated[0]["file_path"])
    assert os.path.exists(test_abs_path)
    
    with open(test_abs_path, "r", encoding="utf-8") as f:
        code = f.read()
    
    # AST parse using javalang to verify Java syntax is completely correct
    tree = javalang.parse.parse(code)
    assert tree is not None

def test_stage3_generation_python(mock_repo_dir):
    config = {"models": {"stage3": "kimi/kimi-k2.6"}}
    os.environ["OPENROUTER_API_KEY"] = "your-openrouter-api-key-here"
    
    stage3 = Stage3Generation(config)
    
    initial_state = AgentState(
        repo_path=mock_repo_dir,
        language="python",
        framework="fastapi",
        service_files=["app/services/product_service.py"],
        analysis_result={
            "services": [
                {
                    "class_name": "ProductService",
                    "package": "",
                    "file_path": "app/services/product_service.py",
                    "methods": [{"name": "get_product_name", "return_type": "str", "params": [{"name": "product_id", "type": "int"}]}],
                    "dependencies": []
                }
            ]
        },
        test_plan=MOCK_TEST_PLAN_PYTHON,
        generated_tests=[],
        coverage_report=None,
        retry_count=0,
        history=[]
    )
    
    final_state = stage3.run(initial_state)
    
    generated = final_state["generated_tests"]
    assert len(generated) == 1
    assert generated[0]["service"] == "ProductService"
    assert "test_product_service.py" in generated[0]["file_path"]
    
    test_abs_path = os.path.join(mock_repo_dir, generated[0]["file_path"])
    assert os.path.exists(test_abs_path)
    
    # Verify Python syntax using compile
    with open(test_abs_path, "r", encoding="utf-8") as f:
        code = f.read()
    
    compile(code, "<string>", "exec") # should not throw Exception
