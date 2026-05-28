import os
import json
import logging
from typing import Dict, Any, List
from jsonschema import validate

from agent.state import AgentState
from agent.llm.client import OpenRouterClient, clean_json_response
from agent.llm.prompts import STAGE2_SYSTEM_PROMPT, STAGE2_USER_PROMPT_TEMPLATE
from agent.progress import update_progress

logger = logging.getLogger(__name__)

def _extract_exception_string(t: Any) -> str:
    if isinstance(t, dict):
        # 1. Search for any string value that looks like an Exception class name
        for v in t.values():
            if isinstance(v, str) and any(suffix in v for suffix in ["Error", "Exception", "Fail", "Err", "Exc"]):
                return v
        # 2. Search for keys containing type, class, name, exc, error
        for k, v in t.items():
            if isinstance(k, str) and any(term in k.lower() for term in ["type", "class", "name", "exc", "error"]):
                if isinstance(v, str):
                    return v
        # 3. Pick the first string value
        for v in t.values():
            if isinstance(v, str):
                return v
        # 4. Ultimate fallback
        return str(t)
    return str(t)

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
        update_progress(2, 10, "Bắt đầu lập kế hoạch kiểm thử (Test Planning)...")

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
            update_progress(2, 40, "Đang khởi tạo kế hoạch kiểm thử mặc định (Local fallback)...")
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

                update_progress(2, 30, "Đang chạy mô hình AI DeepSeek V4 để phác thảo các kịch bản kiểm thử...")
                response = self.llm_client.chat_completion(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"}
                )

                from agent.llm.client import robust_json_loads
                cleaned_response = clean_json_response(response)
                test_plan = robust_json_loads(cleaned_response)
            except Exception as e:
                logger.error(f"LLM Test Planning failed: {e}. Falling back to local programmatic generator.")
                update_progress(2, 60, "Phân tích AI thất bại, đang chuyển sang bộ sinh kế hoạch mặc định...")
                test_plan = self.generate_local_fallback_plan(analysis_result)

        # Sanitize test plan to comply with schema constraints
        if test_plan and "test_cases" in test_plan and isinstance(test_plan["test_cases"], list):
            # Keep only valid dict structures in test_cases list
            test_plan["test_cases"] = [tc for tc in test_plan["test_cases"] if isinstance(tc, dict)]
            for tc in test_plan["test_cases"]:
                # Ensure service, method, test_id, description are strings and not None
                for field in ["service", "method", "test_id", "description", "type"]:
                    if field in tc:
                        if tc[field] is None:
                            tc[field] = ""
                        else:
                            tc[field] = str(tc[field])
                
                # Sanitize setup
                if "setup" not in tc or not isinstance(tc["setup"], dict):
                    tc["setup"] = {"mocks": []}
                elif "mocks" not in tc["setup"] or not isinstance(tc["setup"]["mocks"], list):
                    tc["setup"]["mocks"] = []
                    
                for mock in tc["setup"]["mocks"]:
                    if "return_value" in mock:
                        if mock["return_value"] is None:
                            mock["return_value"] = ""
                        else:
                            mock["return_value"] = str(mock["return_value"])

                # Sanitize input
                if "input" not in tc or not isinstance(tc["input"], dict):
                    tc["input"] = {}
                else:
                    tc["input"] = {k: str(v) if v is not None else "null" for k, v in tc["input"].items()}

                # Sanitize expected
                if "expected" not in tc or not isinstance(tc["expected"], dict):
                    tc["expected"] = {"return_type": "void", "assertions": []}
                else:
                    exp = tc["expected"]
                    if "return_type" in exp:
                        if exp["return_type"] is None:
                            exp["return_type"] = "void"
                        else:
                            exp["return_type"] = str(exp["return_type"])
                    else:
                        exp["return_type"] = "void"
                        
                    if "assertions" in exp and isinstance(exp["assertions"], list):
                        exp["assertions"] = [str(a) for a in exp["assertions"] if a is not None]
                    elif "assertions" not in exp:
                        exp["assertions"] = []
                        
                    if "verify_mocks" in exp and isinstance(exp["verify_mocks"], list):
                        exp["verify_mocks"] = [str(vm) for vm in exp["verify_mocks"] if vm is not None]

                    if "throws" in exp:
                        if exp["throws"] is None:
                            exp["throws"] = None
                        else:
                            exp["throws"] = _extract_exception_string(exp["throws"])
                            
                    if "exception_message_contains" in exp:
                        if exp["exception_message_contains"] is not None:
                            exp["exception_message_contains"] = str(exp["exception_message_contains"])

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

        test_cases_count = len(test_plan.get("test_cases", [])) if test_plan else 0
        update_progress(2, 100, f"Đã lập kế hoạch xong {test_cases_count} kịch bản kiểm thử.", {
            "test_cases_count": test_cases_count
        })

        return state

    def generate_local_fallback_plan(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a basic but schema-valid test plan programmatically.
        """
        test_cases = []
        services = analysis_result.get("services", [])
        counters = {}

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

                key = f"{service_name}_{method_name}"

                # 1. Happy Path Test Case
                counters[key] = counters.get(key, 0) + 1
                test_id_happy = f"{key}_{counters[key]:03d}"
                test_cases.append({
                    "service": service_name,
                    "method": method_name,
                    "test_id": test_id_happy,
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
                    
                    counters[key] = counters.get(key, 0) + 1
                    test_id_edge = f"{key}_{counters[key]:03d}"
                    test_cases.append({
                        "service": service_name,
                        "method": method_name,
                        "test_id": test_id_edge,
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
                        
                    counters[key] = counters.get(key, 0) + 1
                    test_id_error = f"{key}_{counters[key]:03d}"
                    test_cases.append({
                        "service": service_name,
                        "method": method_name,
                        "test_id": test_id_error,
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
