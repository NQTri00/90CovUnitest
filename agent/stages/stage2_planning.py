import os
import json
import logging
from typing import Dict, Any, List
from jsonschema import validate

from agent.state import AgentState
from agent.llm.client import OpenRouterClient
from agent.llm.prompts import STAGE2_SYSTEM_PROMPT, STAGE2_USER_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

class Stage2Planning:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_client = OpenRouterClient()
        self.model = config.get("models", {}).get("stage2", "deepseek/deepseek-v4-flash")

    def run(self, state: AgentState) -> AgentState:
        """
        Run Stage 2: Test Planning.
        """
        analysis_result = state.get("analysis_result")
        if not analysis_result:
            raise ValueError("No analysis result found in state. Run Stage 1 first.")

        logger.info("Starting Stage 2: Test Planning")

        # Load Schema
        schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                   "schemas", "test_plan.schema.json")
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load test plan schema: {e}")
            schema = None

        test_plan = None

        # Check API Key
        if not self.llm_client.api_key or self.llm_client.api_key.startswith("your-openrouter-api-key"):
            logger.info("OPENROUTER_API_KEY is not set or mock. Running Local Fallback Plan Generator.")
            test_plan = self.generate_local_fallback_plan(analysis_result)
        else:
            try:
                # Call LLM
                user_prompt = STAGE2_USER_PROMPT_TEMPLATE.format(
                    language=state.get("language", "java"),
                    framework=state.get("framework", "spring-boot"),
                    analysis_json=json.dumps(analysis_result, indent=2)
                )

                messages = [
                    {"role": "system", "content": STAGE2_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]

                response = self.llm_client.chat_completion(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"}
                )

                test_plan = json.loads(response)
            except Exception as e:
                logger.error(f"LLM Test Planning failed: {e}. Falling back to local programmatic generator.")
                test_plan = self.generate_local_fallback_plan(analysis_result)

        # Validate against schema
        if schema and test_plan:
            try:
                validate(instance=test_plan, schema=schema)
                logger.info("test_plan.json successfully validated against schema.")
            except Exception as e:
                logger.error(f"test_plan validation failed: {e}")
                # Log invalid schema format but don't crash if we can avoid it.

        state["test_plan"] = test_plan
        state["history"].append("Stage 2 completed: Test planning done.")

        return state

    def generate_local_fallback_plan(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a basic but schema-valid test plan programmatically.
        """
        test_cases = []
        services = analysis_result.get("services", [])

        for service in services:
            service_name = service.get("class_name", "UnknownService")
            dependencies = service.get("dependencies", [])

            for method in service.get("methods", []):
                method_name = method.get("name", "unknownMethod")
                
                # Skip simple getters/setters/toString if visibility is not public or method is generic
                if method.get("priority") == "LOW" and method_name.startswith(("get", "set", "toString", "hashCode", "equals")):
                    continue

                # Prepare standard mocks
                mocks = []
                for dep in dependencies:
                    dep_name = dep.get("field_name", "dependency")
                    # Make a guess of method names depending on category
                    mock_method = "findById" if dep.get("category") == "repository" else "call"
                    mocks.append({
                        "dependency": dep_name,
                        "method": mock_method,
                        "behavior": "return",
                        "return_value": f"mock{dep.get('type', 'Object')}"
                    })

                # Prepare method inputs
                inputs = {}
                for idx, p in enumerate(method.get("params", [])):
                    p_name = p.get("name", f"param{idx}")
                    p_type = p.get("type", "String")
                    
                    # Deduce default values
                    val = "1L" if "Long" in p_type or "int" in p_type or "Integer" in p_type else '"test"'
                    inputs[p_name] = val

                # 1. Happy Path Test Case
                test_cases.append({
                    "service": service_name,
                    "method": method_name,
                    "test_id": f"{service_name}_{method_name}_001",
                    "type": "happy_path",
                    "description": f"Chạy thành công phương thức {method_name} với tham số hợp lệ",
                    "setup": {
                        "mocks": mocks
                    },
                    "input": inputs,
                    "expected": {
                        "return_type": method.get("return_type", "void"),
                        "assertions": [
                            "result != null" if method.get("return_type") != "void" else "true"
                        ],
                        "verify_mocks": [
                            f"{m['dependency']}.{m['method']}() called once" for m in mocks
                        ]
                    }
                })

                # 2. Edge Case Test Case (if parameters exist)
                if method.get("params"):
                    edge_inputs = {}
                    for p in method.get("params", []):
                        p_name = p.get("name")
                        edge_inputs[p_name] = "null"
                    
                    test_cases.append({
                        "service": service_name,
                        "method": method_name,
                        "test_id": f"{service_name}_{method_name}_002",
                        "type": "edge_case",
                        "description": f"Kiểm tra phương thức {method_name} với đầu vào null",
                        "setup": {
                            "mocks": []
                        },
                        "input": edge_inputs,
                        "expected": {
                            "return_type": method.get("return_type", "void"),
                            "assertions": [
                                "result == null" if method.get("return_type") != "void" else "true"
                            ],
                            "throws": "IllegalArgumentException" if method.get("throws") else None,
                            "exception_message_contains": None
                        }
                    })

                # 3. Error Path Test Case (if exceptions or dependencies exist)
                if method.get("throws") or dependencies:
                    error_mocks = []
                    thrown_exc = "RuntimeException"
                    
                    if method.get("throws"):
                        thrown_exc = method.get("throws")[0]
                        
                    for dep in dependencies:
                        dep_name = dep.get("field_name")
                        error_mocks.append({
                            "dependency": dep_name,
                            "method": "findById" if dep.get("category") == "repository" else "call",
                            "behavior": "throw",
                            "return_value": thrown_exc
                        })
                        
                    test_cases.append({
                        "service": service_name,
                        "method": method_name,
                        "test_id": f"{service_name}_{method_name}_003" if method.get("params") else f"{service_name}_{method_name}_002",
                        "type": "error_path",
                        "description": f"Xử lý lỗi ném exception {thrown_exc} từ dependencies",
                        "setup": {
                            "mocks": error_mocks
                        },
                        "input": inputs,
                        "expected": {
                            "return_type": method.get("return_type", "void"),
                            "assertions": [],
                            "throws": thrown_exc,
                            "exception_message_contains": None
                        }
                    })

        return {
            "plan_version": "1.0",
            "target_coverage": 90,
            "test_cases": test_cases
        }
