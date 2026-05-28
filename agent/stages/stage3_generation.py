import os
import re
import json
import logging
import py_compile
import subprocess
import javalang
from typing import Dict, Any, List, Tuple, Optional

from agent.state import AgentState
from agent.llm.client import OpenRouterClient
from agent.llm.prompts import (
    STAGE3_SYSTEM_PROMPT_JAVA,
    STAGE3_SYSTEM_PROMPT_PYTHON,
    STAGE3_USER_PROMPT_TEMPLATE,
    STAGE3_AUTO_FIX_PROMPT
)
from agent.progress import update_progress

logger = logging.getLogger(__name__)

class Stage3Generation:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_client = OpenRouterClient()
        self.model = config.get("models", {}).get("stage3", "kimi/kimi-k2.6")
        self.fallback_model = config.get("models", {}).get("stage3_fallback", "deepseek/deepseek-v4-pro")

    def run(self, state: AgentState) -> AgentState:
        """
        Run Stage 3: Test Generation.
        """
        test_plan = state.get("test_plan")
        if not test_plan:
            raise ValueError("No test plan found in state. Run Stage 2 first.")

        repo_path = state.get("repo_path")
        language = state.get("language", "java")
        framework = state.get("framework", "spring-boot")

        logger.info(f"Starting Stage 3: Test Generation for {language} project.")
        update_progress(3, 10, "Bắt đầu sinh mã nguồn kiểm thử (Test Generation)...")

        # Group test cases by service name
        service_test_cases = {}
        for tc in test_plan.get("test_cases", []):
            service_name = tc.get("service")
            if service_name not in service_test_cases:
                service_test_cases[service_name] = []
            service_test_cases[service_name].append(tc)

        generated_files = []
        failed_services = []

        # Target output folder
        output_base_dir = os.path.join(repo_path, "generated_tests")
        os.makedirs(output_base_dir, exist_ok=True)

        # Write run header separator to failed_methods.log
        log_path = os.path.join(repo_path, "failed_methods.log")
        try:
            from datetime import datetime
            with open(log_path, "a", encoding="utf-8") as lf:
                lf.write(f"\n=== Run {datetime.now().isoformat()} ===\n")
        except Exception as e:
            logger.error(f"Failed to write header to failed_methods.log: {e}")

        services_analysis = state.get("analysis_result", {}).get("services", [])
        services_by_name = {s["class_name"]: s for s in services_analysis}

        total_services = len(service_test_cases)
        for idx, (service_name, tcs) in enumerate(service_test_cases.items()):
            percentage = 10 + int((idx) / max(total_services, 1) * 80)
            update_progress(3, percentage, f"Đang tạo test case cho dịch vụ ({idx+1}/{total_services}): {service_name}", {
                "generating_service": service_name,
                "generated_files": [f["file_path"] for f in generated_files]
            })

            service_meta = services_by_name.get(service_name)
            if not service_meta:
                logger.warning(f"Metadata for service {service_name} not found in analysis. Skipping.")
                continue

            rel_file_path = service_meta.get("file_path")
            abs_file_path = os.path.join(repo_path, rel_file_path)
            
            try:
                with open(abs_file_path, "r", encoding="utf-8") as f:
                    source_code = f.read()
            except Exception as e:
                logger.error(f"Failed to read service source file {abs_file_path}: {e}")
                continue

            test_file_content = None

            # Check if LLM key is absent or mock
            if not self.llm_client.api_key or self.llm_client.api_key.startswith("your-openrouter-api-key"):
                logger.info(f"Generating test file offline (Local Fallback) for {service_name}.")
                test_file_content = self.generate_local_fallback_code(service_meta, tcs, language)
            else:
                # Call LLM to generate code
                test_file_content = self.generate_llm_code_with_autofix(
                    service_name=service_name,
                    source_code=source_code,
                    tcs=tcs,
                    language=language,
                    framework=framework
                )

            if test_file_content:
                # Write to the mirrored directory structure
                test_rel_path = self.get_test_file_relative_path(rel_file_path, language)
                test_abs_path = os.path.join(output_base_dir, test_rel_path)
                
                os.makedirs(os.path.dirname(test_abs_path), exist_ok=True)
                try:
                    with open(test_abs_path, "w", encoding="utf-8") as f:
                        f.write(test_file_content)
                    logger.info(f"Saved generated test file to {test_abs_path}")
                    generated_files.append({
                        "service": service_name,
                        "file_path": os.path.relpath(test_abs_path, repo_path)
                    })
                except Exception as e:
                    logger.error(f"Failed to write test file {test_abs_path}: {e}")
                    failed_services.append(service_name)
            else:
                failed_services.append(service_name)
                # Write failed status to failed_methods.log
                log_path = os.path.join(repo_path, "failed_methods.log")
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(f"Generation failed for service: {service_name}\n")

        state["generated_tests"] = generated_files
        state["history"].append(f"Stage 3 completed: Generated {len(generated_files)} test files.")

        update_progress(3, 100, f"Đã sinh xong bộ test cho {len(generated_files)} dịch vụ.", {
            "generated_files": [f["file_path"] for f in generated_files]
        })

        return state

    def generate_llm_code_with_autofix(
        self,
        service_name: str,
        source_code: str,
        tcs: List[Dict[str, Any]],
        language: str,
        framework: str
    ) -> Optional[str]:
        """
        Query LLM to generate test class, checking syntax and requesting auto-fixes on error.
        """
        system_prompt = STAGE3_SYSTEM_PROMPT_JAVA if language == "java" else STAGE3_SYSTEM_PROMPT_PYTHON
        user_prompt = STAGE3_USER_PROMPT_TEMPLATE.format(
            source_code=source_code,
            test_cases_json=json.dumps(tcs, indent=2)
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        current_model = self.model
        code_block_lang = "java" if language == "java" else "python"

        for attempt in range(4): # 1 initial gen + 3 auto-fixes
            try:
                response = self.llm_client.chat_completion(
                    messages=messages,
                    model=current_model,
                    temperature=0.1
                )
                
                # Parse markdown code block
                code = self.extract_code_block(response, code_block_lang)
                if not code:
                    raise ValueError("Failed to extract code block from LLM response.")

                # Perform syntax check
                is_valid, err_msg = self.check_syntax(code, language)
                if is_valid:
                    return code

                logger.warning(f"Syntax check failed for {service_name} on attempt {attempt + 1}: {err_msg}")
                
                # Setup messages for auto-fix
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": STAGE3_AUTO_FIX_PROMPT.format(error_message=err_msg, source_code=code)
                })
                
                # Fallback to stronger model if Kimi fails repeatedly
                if attempt >= 1:
                    current_model = self.fallback_model
                    
            except Exception as e:
                logger.error(f"Error during code generation attempt {attempt + 1}: {e}")
                if attempt == 3:
                    return None
                    
        return None

    def extract_code_block(self, text: str, lang: str) -> Optional[str]:
        """
        Extract content inside ```lang ... ``` or return text if no block found.
        """
        if not text:
            return None
            
        # Try to find standard closed code blocks first
        pattern = rf"```(?:{lang})?\s*(.*?)\s*```"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
            
        # Check if there is an unclosed code block (common on truncation)
        start_patterns = [
            rf"```(?:{lang})\b",
            rf"```"
        ]
        for start_pat in start_patterns:
            match_start = re.search(start_pat, text, re.IGNORECASE)
            if match_start:
                start_idx = match_start.end()
                code_part = text[start_idx:].strip()
                if "```" in code_part:
                    code_part = code_part.split("```")[0].strip()
                return code_part

        # Fallback: if no code block markers at all, try to find the first occurrence of import / package
        # and strip any conversational prefix.
        lines = text.splitlines()
        code_lines = []
        started = False
        for line in lines:
            if started:
                code_lines.append(line)
            else:
                stripped = line.strip()
                if (
                    stripped.startswith("import ") or 
                    stripped.startswith("from ") or 
                    stripped.startswith("def ") or 
                    stripped.startswith("class ") or 
                    stripped.startswith("package ") or 
                    stripped.startswith("public class ") or
                    stripped.startswith("@")
                ):
                    started = True
                    code_lines.append(line)
                    
        if code_lines:
            return "\n".join(code_lines).strip()
            
        # Last resort fallback
        if "package " in text or "import " in text or "def test_" in text:
            return text.strip()
            
        return None

    def check_syntax(self, code: str, language: str) -> Tuple[bool, str]:
        """
        Validate syntax of the generated code.
        """
        if language == "python":
            try:
                # Compiling Python code locally using AST
                compile(code, "<string>", "exec")
                return True, ""
            except Exception as e:
                return False, str(e)
        elif language == "java":
            try:
                # Validating Java code using javalang parser (lightweight AST parse)
                javalang.parse.parse(code)
                return True, ""
            except Exception as e:
                return False, str(e)
        return True, ""

    def get_test_file_relative_path(self, rel_source_path: str, language: str) -> str:
        """
        Convert src/main/java/.../UserService.java -> com/.../UserServiceTest.java
        or myapp/services/user_service.py -> test_user_service.py
        """
        base_name = os.path.basename(rel_source_path)
        
        if language == "java":
            # Strip src/main/java/ or src/ from path
            clean_path = rel_source_path
            for prefix in ["src/main/java/", "src/test/java/", "src/"]:
                if clean_path.startswith(prefix):
                    clean_path = clean_path[len(prefix):]
                    break
            
            # Replace ClassName.java with ClassNameTest.java
            dir_name = os.path.dirname(clean_path)
            file_name = base_name.replace(".java", "Test.java")
            return os.path.join(dir_name, file_name)
            
        elif language == "python":
            # Replace user_service.py with test_user_service.py
            dir_name = os.path.dirname(rel_source_path)
            # Remove src/ or app/ prefix if we want a flat test structure,
            # but mirror is requested, so we keep the folder and prepend test_ to file
            file_name = f"test_{base_name}"
            return os.path.join(dir_name, file_name)

        return base_name

    def generate_local_fallback_code(self, service_meta: Dict[str, Any], tcs: List[Dict[str, Any]], language: str) -> str:
        """
        Offline generator that builds clean, compilable template tests.
        """
        service_name = service_meta.get("class_name")
        package_name = service_meta.get("package", "")
        dependencies = service_meta.get("dependencies", [])

        if language == "java":
            # Generate Java JUnit 5 class
            mocks_decls = []
            for dep in dependencies:
                mocks_decls.append(f"    @Mock\n    private {dep['type']} {dep['field_name']};")
                
            test_methods = []
            for tc in tcs:
                method_name = tc.get("method")
                test_id = tc.get("test_id")
                test_type = tc.get("type")
                desc = tc.get("description")
                
                # Mock setups inside test method
                setup_lines = []
                for m in tc.get("setup", {}).get("mocks", []):
                    # when(repo.findById(1L)).thenReturn(Optional.of(mockUser));
                    ret_val = m.get("return_value")
                    beh = m.get("behavior")
                    if beh == "return":
                        setup_lines.append(f"        // Mock behavior: return {ret_val}")
                    elif beh == "throw":
                        setup_lines.append(f"        // Mock behavior: throw new {ret_val}()")

                # Input parameters
                inputs = tc.get("input", {})
                inputs_str = ", ".join(inputs.values())

                # Expected
                expected = tc.get("expected", {})
                assertions = []
                for ass in expected.get("assertions", []):
                    assertions.append(f"        // Assert: {ass}")
                
                throws = expected.get("throws")
                if throws:
                    test_body = f"""    @Test
    @DisplayName("{desc}")
    public void should_{method_name}_{test_id.split('_')[-1]}() {{
        // Arrange
{chr(10).join(setup_lines)}

        // Act & Assert
        assertThrows({throws}.class, () -> {{
            {service_name[0].lower() + service_name[1:]}.{method_name}({inputs_str});
        }});
    }}"""
                else:
                    test_body = f"""    @Test
    @DisplayName("{desc}")
    public void should_{method_name}_{test_id.split('_')[-1]}() {{
        // Arrange
{chr(10).join(setup_lines)}

        // Act
        var result = {service_name[0].lower() + service_name[1:]}.{method_name}({inputs_str});

        // Assert
        assertNotNull(result);
{chr(10).join(assertions)}
    }}"""
                test_methods.append(test_body)

            # Compile full Java class
            package_stmt = f"package {package_name};\n\n" if package_name else ""
            return f"""{package_stmt}import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.InjectMocks;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
public class {service_name}Test {{

{chr(10).join(mocks_decls)}

    @InjectMocks
    private {service_name} {service_name[0].lower() + service_name[1:]};

{chr(10).join(test_methods)}
}}
"""

        elif language == "python":
            # Generate Pytest file
            # Setup mock fixtures
            fixtures = []
            mock_names = []
            for dep in dependencies:
                f_name = f"mock_{dep['field_name']}"
                mock_names.append(f_name)
                fixtures.append(f"""@pytest.fixture
def {f_name}():
    return MagicMock()""")

            # Service fixture
            dep_args = ", ".join([f"{dep['field_name']}={f_name}" for dep, f_name in zip(dependencies, mock_names)])
            service_var = service_name[0].lower() + service_name[1:]
            
            fixtures.append(f"""@pytest.fixture
def {service_var}_instance({', '.join(mock_names)}):
    from {service_meta['file_path'].replace('/', '.').replace('.py', '')} import {service_name}
    return {service_name}({', '.join(mock_names)})""")

            # Test methods
            test_funcs = []
            for tc in tcs:
                method_name = tc.get("method")
                test_id = tc.get("test_id")
                test_type = tc.get("type")
                desc = tc.get("description")
                
                # Mock setups
                setup_lines = []
                for m in tc.get("setup", {}).get("mocks", []):
                    ret_val = m.get("return_value")
                    beh = m.get("behavior")
                    dep_arg_name = f"mock_{m['dependency']}"
                    if beh == "return":
                        setup_lines.append(f"    # Mock: {dep_arg_name}.{m['method']}.return_value = {ret_val}")
                    elif beh == "throw":
                        setup_lines.append(f"    # Mock: {dep_arg_name}.{m['method']}.side_effect = {ret_val}()")

                inputs = tc.get("input", {})
                inputs_str = ", ".join([f"{k}={v}" for k, v in inputs.items()])

                expected = tc.get("expected", {})
                assertions = []
                for ass in expected.get("assertions", []):
                    assertions.append(f"    # Assert: {ass}")
                
                throws = expected.get("throws")
                if throws:
                    test_func = f"""def test_{method_name}_{test_id.split('_')[-1]}({service_var}_instance, {', '.join(mock_names)}):
    \"\"\"{desc}\"\"\"
{chr(10).join(setup_lines)}
    import pytest
    with pytest.raises(Exception):
        {service_var}_instance.{method_name}({inputs_str})
"""
                else:
                    test_func = f"""def test_{method_name}_{test_id.split('_')[-1]}({service_var}_instance, {', '.join(mock_names)}):
    \"\"\"{desc}\"\"\"
{chr(10).join(setup_lines)}
    result = {service_var}_instance.{method_name}({inputs_str})
    assert result is not None
{chr(10).join(assertions)}
"""
                test_funcs.append(test_func)

            return f"""import pytest
from unittest.mock import MagicMock

{chr(10).join(fixtures)}

{chr(10).join(test_funcs)}
"""

        return ""
