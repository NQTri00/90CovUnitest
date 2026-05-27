import os
import json
import logging
from typing import Dict, Any, List, Tuple, Optional
from jsonschema import validate

from agent.state import AgentState
from agent.parsers.java_parser import JavaParser
from agent.parsers.python_parser import PythonParser
from agent.llm.client import OpenRouterClient
from agent.llm.prompts import STAGE1_SYSTEM_PROMPT, STAGE1_USER_PROMPT_TEMPLATE
from agent.progress import update_progress

logger = logging.getLogger(__name__)

class Stage1Analysis:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_client = OpenRouterClient()
        self.model = config.get("models", {}).get("stage1", "kimi/kimi-k2.6")

    def run(self, state: AgentState) -> AgentState:
        """
        Run Stage 1: Code Analysis.
        """
        repo_path = state.get("repo_path")
        if not repo_path or not os.path.exists(repo_path):
            raise ValueError(f"Repository path does not exist: {repo_path}")

        logger.info(f"Starting Stage 1: Code Analysis on {repo_path}")
        update_progress(1, 5, "Khởi chạy phân tích cấu trúc dự án...")

        # Step 1.1: Language & Framework Detection
        language, framework, build_tool = self.detect_language_and_framework(repo_path)
        logger.info(f"Detected: language={language}, framework={framework}, build_tool={build_tool}")
        update_progress(1, 15, f"Đã nhận diện: {language.upper()} ({framework.upper()})")

        # Step 1.2: Source File Discovery
        service_files = self.discover_service_files(repo_path, language)
        logger.info(f"Discovered {len(service_files)} service files to analyze.")
        update_progress(1, 20, f"Đã phát hiện {len(service_files)} tệp tin cần phân tích.", {"service_files": service_files})

        services_metadata = []

        # Load Schema for validation
        schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                   "schemas", "analysis_result.schema.json")
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load analysis schema: {e}")
            schema = None

        # Step 1.3 & 1.4: Parse and Enrich
        for idx, file_path in enumerate(service_files):
            percentage = 20 + int((idx + 1) / max(len(service_files), 1) * 70)
            update_progress(1, percentage, f"Đang phân tích tệp ({idx+1}/{len(service_files)}): {file_path}", {
                "analyzing_file": file_path,
                "analyzed_files": [s["file_path"] for s in services_metadata]
            })

            abs_path = os.path.join(repo_path, file_path)
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    source_code = f.read()
            except Exception as e:
                logger.error(f"Failed to read file {file_path}: {e}")
                continue

            # Local AST parse fallback
            local_parse = None
            if language == "java":
                local_parse = JavaParser.parse_file(file_path, source_code)
            elif language == "python":
                parser = PythonParser(file_path, source_code)
                parsed_classes = parser.parse()
                if parsed_classes:
                    local_parse = parsed_classes[0]  # Take the first class

            # If LLM key is missing, use local parse directly
            if not self.llm_client.api_key or self.llm_client.api_key.startswith("your-openrouter-api-key"):
                if local_parse:
                    services_metadata.append(self.sanitize_service_metadata(local_parse, file_path))
                continue

            # LLM-based enrichment
            llm_result = self.call_llm_analysis(file_path, source_code, language, framework, local_parse)
            
            if llm_result:
                services_metadata.append(self.sanitize_service_metadata(llm_result, file_path))
            elif local_parse:
                # LLM failed, fallback to local AST parse
                logger.warning(f"LLM analysis failed for {file_path}. Falling back to local AST.")
                services_metadata.append(self.sanitize_service_metadata(local_parse, file_path))

        analysis_result = {
            "repo": {
                "path": repo_path,
                "language": language,
                "framework": framework,
                "version": None,
                "build_tool": build_tool
            },
            "services": services_metadata
        }

        # Validate JSON output against schema
        if schema:
            try:
                validate(instance=analysis_result, schema=schema)
                logger.info("analysis_result.json successfully validated against schema.")
            except Exception as e:
                logger.error(f"analysis_result validation failed: {e}")
                # We still set it, but log the warning
        
        state["language"] = language
        state["framework"] = framework
        state["service_files"] = service_files
        state["analysis_result"] = analysis_result
        state["history"].append("Stage 1 completed: Code analysis done.")

        update_progress(1, 100, "Hoàn thành Stage 1: Phân tích mã nguồn.", {
            "analyzed_files": [s["file_path"] for s in services_metadata]
        })
        return state

    def detect_language_and_framework(self, repo_path: str) -> Tuple[str, str, str]:
        """
        Detect project language, framework and build tool.
        """
        # Exclude typical folders
        files = []
        for root, dirs, filenames in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in ["venv", ".venv", "node_modules", ".git", "build", "target"]]
            for f in filenames:
                files.append(f)

        # Java check
        if "pom.xml" in files:
            return "java", "spring-boot", "maven"
        if "build.gradle" in files or "build.gradle.kts" in files:
            return "java", "spring-boot", "gradle"

        # Node / TS check
        if "package.json" in files:
            # Simple assumption, could parse package.json to find framework
            return "typescript", "nestjs", "npm"

        # Python check
        if any(f in files for f in ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]):
            # Simple assumption FastAPI
            return "python", "fastapi", "pip"

        # Default fallback
        return "unknown", "unknown", "unknown"

    def discover_service_files(self, repo_path: str, language: str) -> List[str]:
        """
        Find candidate service files.
        """
        service_files = []
        for root, dirs, files in os.walk(repo_path):
            # Exclude folders
            dirs[:] = [d for d in dirs if d not in ["venv", ".venv", "node_modules", ".git", "build", "target", "tests", "test", "generated_tests"]]
            
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), repo_path)
                
                # Check extension and name patterns
                if language == "java" and file.endswith(".java"):
                    # Check if file has service keywords or @Service annotation
                    if "Service" in file or "service" in rel_path.lower():
                        # Exclude test files
                        if "Test.java" not in file and "Tests.java" not in file:
                            service_files.append(rel_path)
                elif language == "python" and file.endswith(".py"):
                    if "service" in file.lower() or "service" in rel_path.lower():
                        # Exclude tests
                        if not file.startswith("test_") and not file.endswith("_test.py"):
                            service_files.append(rel_path)
                elif language == "typescript" and file.endswith(".ts"):
                    if "service" in file.lower():
                        if ".spec.ts" not in file and ".test.ts" not in file:
                            service_files.append(rel_path)

        # Fallback if no matching service files found
        if not service_files:
            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [d for d in dirs if d not in ["venv", ".venv", "node_modules", ".git", "build", "target", "tests", "test", "generated_tests"]]
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), repo_path)
                    if language == "python" and file.endswith(".py"):
                        if not file.startswith("test_") and not file.endswith("_test.py") and not file.startswith("__") and file != "setup.py":
                            service_files.append(rel_path)
                    elif language == "java" and file.endswith(".java"):
                        if "Test.java" not in file and "Tests.java" not in file and not "Mock" in file:
                            service_files.append(rel_path)
                            
        return service_files

    def call_llm_analysis(
        self,
        file_path: str,
        source_code: str,
        language: str,
        framework: str,
        local_parse_context: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Call Kimi K2.6 to perform structured analysis.
        """
        dependency_context = ""
        if local_parse_context:
            dependency_context = f"Cấu trúc trích xuất AST sơ bộ:\n{json.dumps(local_parse_context, indent=2)}"

        user_prompt = STAGE1_USER_PROMPT_TEMPLATE.format(
            file_path=file_path,
            language=language,
            framework=framework,
            source_code=source_code,
            dependency_context=dependency_context
        )

        messages = [
            {"role": "system", "content": STAGE1_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self.llm_client.chat_completion(
                messages=messages,
                model=self.model,
                response_format={"type": "json_object"}
            )
            # Parse json output
            from agent.llm.client import clean_json_response
            cleaned_response = clean_json_response(response)
            result = json.loads(cleaned_response)
            return result
        except Exception as e:
            logger.error(f"LLM request failed for {file_path}: {e}")
            return None

    def sanitize_service_metadata(self, raw_metadata: Dict[str, Any], default_file_path: str = "") -> Dict[str, Any]:
        """
        Sanitize and guarantee keys are present in service metadata object.
        """
        sanitized = {
            "class_name": raw_metadata.get("class_name") or "Unknown",
            "package": raw_metadata.get("package") or "",
            "file_path": raw_metadata.get("file_path") or default_file_path,
            "annotations": raw_metadata.get("annotations", []),
            "methods": [],
            "dependencies": []
        }

        # Methods sanitization
        for m in raw_metadata.get("methods", []):
            sanitized_m = {
                "name": m.get("name", "unknown"),
                "visibility": m.get("visibility", "public"),
                "params": [],
                "return_type": m.get("return_type", "void"),
                "throws": m.get("throws", []),
                "annotations": m.get("annotations", []),
                "complexity": int(m.get("complexity", 1)),
                "priority": m.get("priority", "MEDIUM")
            }
            # Params
            for p in m.get("params", []):
                sanitized_m["params"].append({
                    "name": p.get("name", "arg"),
                    "type": p.get("type", "Any")
                })
            sanitized["methods"].append(sanitized_m)

        # Dependencies sanitization
        for d in raw_metadata.get("dependencies", []):
            cat = d.get("category", "service")
            if cat not in ["repository", "http_client", "message_queue", "cache", "service", "utility"]:
                cat = "service"
            
            sanitized["dependencies"].append({
                "field_name": d.get("field_name", "dependency"),
                "type": d.get("type", "Any"),
                "category": cat,
                "mock_strategy": d.get("mock_strategy", "Mock"),
                "annotations": d.get("annotations", [])
            })

        return sanitized
