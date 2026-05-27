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
            dirs[:] = [d for d in dirs if d not in ["venv", ".venv", "node_modules", ".git", "build", "target", "frontend", "front-end", "ui", "client"]]
            for f in filenames:
                files.append(f)

        # Java check
        if "pom.xml" in files:
            return "java", "spring-boot", "maven"
        if "build.gradle" in files or "build.gradle.kts" in files:
            return "java", "spring-boot", "gradle"

        # Python check
        if any(f in files for f in ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]):
            # Simple assumption FastAPI
            return "python", "fastapi", "pip"

        # Node / TS check
        if "package.json" in files:
            # Simple assumption, could parse package.json to find framework
            return "typescript", "nestjs", "npm"

        # Default fallback
        return "unknown", "unknown", "unknown"

    def _score_python_content(self, code_content: str) -> int:
        import ast
        try:
            tree = ast.parse(code_content)
        except Exception:
            return 0
            
        score = 0
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        has_class_with_2_public_methods = False
        has_init_with_params = False
        
        for cls in classes:
            public_methods_count = 0
            for node in cls.body:
                if isinstance(node, ast.FunctionDef):
                    method_name = node.name
                    if method_name == "__init__":
                        args = node.args.args
                        args_without_self = [arg.arg for arg in args if arg.arg != "self"]
                        has_other_args = (
                            len(args_without_self) > 0 or 
                            node.args.vararg is not None or 
                            node.args.kwarg is not None or 
                            len(node.args.kwonlyargs) > 0
                        )
                        if has_other_args:
                            has_init_with_params = True
                    elif not method_name.startswith("_"):
                        public_methods_count += 1
            if public_methods_count >= 2:
                has_class_with_2_public_methods = True

        if has_class_with_2_public_methods:
            score += 40
            
        if has_init_with_params:
            score += 10

        control_structures = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.Try)):
                control_structures += 1
                
        if control_structures >= 3:
            score += 20
            
        is_all_data_only = True
        if classes:
            for cls in classes:
                is_dataclass = False
                for dec in cls.decorator_list:
                    dec_name = ""
                    if isinstance(dec, ast.Name):
                        dec_name = dec.id
                    elif isinstance(dec, ast.Attribute):
                        dec_name = dec.attr
                    if "dataclass" in dec_name.lower():
                        is_dataclass = True
                        break
                        
                is_pydantic = False
                for base in cls.bases:
                    base_name = ""
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if "basemodel" in base_name.lower():
                        is_pydantic = True
                        break
                        
                if is_dataclass or is_pydantic:
                    continue
                    
                class_methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)]
                is_class_trivial = True
                for m in class_methods:
                    is_method_trivial = False
                    if not m.body:
                        is_method_trivial = True
                    elif len(m.body) == 1:
                        stmt = m.body[0]
                        if isinstance(stmt, (ast.Pass, ast.Expr)):
                            is_method_trivial = True
                        elif isinstance(stmt, ast.Return):
                            is_method_trivial = True
                        elif isinstance(stmt, ast.Assign):
                            is_method_trivial = True
                    
                    if not is_method_trivial:
                        is_class_trivial = False
                        break
                
                if not is_class_trivial:
                    is_all_data_only = False
                    break
        else:
            is_all_data_only = False
            
        if is_all_data_only and classes:
            score -= 40
            
        lines = code_content.splitlines()
        if not classes and len(lines) < 50:
            score -= 30
            
        return score

    def _score_java_content(self, code_content: str) -> int:
        import javalang
        try:
            tree = javalang.parse.parse(code_content)
        except Exception:
            return 0
            
        score = 0
        has_target_annotation = False
        target_annotations = {"Service", "Component", "Repository", "RestController", "Controller", "UseCase"}
        public_methods_count = 0
        decision_points = 0
        classes = []
        
        try:
            for path, node in tree.filter(javalang.tree.ClassDeclaration):
                classes.append(node)
                annotations = getattr(node, "annotations", []) or []
                for annotation in annotations:
                    if annotation.name in target_annotations:
                        has_target_annotation = True
                            
                methods = getattr(node, "methods", []) or []
                for method in methods:
                    modifiers = getattr(method, "modifiers", set()) or set()
                    if not modifiers or "public" in modifiers:
                        public_methods_count += 1
                            
            if has_target_annotation:
                score += 40
            if public_methods_count >= 2:
                score += 30
                
            for path, node in tree:
                if isinstance(node, (javalang.tree.IfStatement, 
                                     javalang.tree.ForStatement, 
                                     javalang.tree.WhileStatement, 
                                     javalang.tree.DoStatement, 
                                     javalang.tree.CatchClause, 
                                     javalang.tree.SwitchStatementCase)):
                    decision_points += 1
                    
            total_methods = 0
            for cls in classes:
                methods = getattr(cls, "methods", []) or []
                total_methods += len(methods)
                    
            if (total_methods + decision_points) >= 3:
                score += 20
        except Exception:
            pass
            
        is_all_data_only = True
        if classes:
            for cls in classes:
                is_lombok = False
                annotations = getattr(cls, "annotations", []) or []
                for annotation in annotations:
                    if annotation.name in {"Data", "Value", "Getter", "Setter", "ToString", "EqualsAndHashCode"}:
                        is_lombok = True
                        break
                if is_lombok:
                    continue
                    
                if type(cls).__name__ == "RecordDeclaration":
                    continue
                    
                is_class_trivial = True
                methods = getattr(cls, "methods", []) or []
                if methods:
                    for m in methods:
                        body = getattr(m, "body", []) or []
                        if not body:
                            continue
                        if len(body) > 1:
                            is_class_trivial = False
                            break
                        stmt = body[0]
                        is_stmt_trivial = False
                        if isinstance(stmt, javalang.tree.ReturnStatement):
                            is_stmt_trivial = True
                        elif isinstance(stmt, javalang.tree.BlockStatement):
                            statements = getattr(stmt, "statements", []) or []
                            if not statements:
                                is_stmt_trivial = True
                            elif len(statements) == 1:
                                sub_stmt = statements[0]
                                if isinstance(sub_stmt, (javalang.tree.ReturnStatement, javalang.tree.StatementExpression)):
                                    is_stmt_trivial = True
                        elif isinstance(stmt, javalang.tree.StatementExpression):
                            is_stmt_trivial = True
                            
                        if not is_stmt_trivial:
                            is_class_trivial = False
                            break
                if not is_class_trivial:
                    is_all_data_only = False
                    break
        else:
            is_all_data_only = False
            
        if is_all_data_only and classes:
            score -= 40
            
        lines = code_content.splitlines()
        if not classes and len(lines) < 50:
            score -= 30
            
        return score

    def discover_service_files(self, repo_path: str, language: str) -> List[str]:
        """
        Find candidate service files.
        """
        import os
        
        target_ext = ".py"
        if language == "java":
            target_ext = ".java"
        elif language == "typescript":
            target_ext = ".ts"
            
        candidate_files = []
        excluded_dirs = {"venv", ".venv", ".git", "node_modules", "build", "target", "tests", "test", "generated_tests", "migrations", "alembic", "__pycache__", "frontend", "front-end", "ui", "client"}
        
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in excluded_dirs]
            
            for file in files:
                if not file.endswith(target_ext):
                    continue
                    
                rel_path = os.path.relpath(os.path.join(root, file), repo_path)
                
                # Step 1: Hard exclude
                if (
                    file.startswith("test_") or
                    file.endswith(("_test.py", "Test.java", "Tests.java")) or
                    file in ["conftest.py", "setup.py", "manage.py", "wsgi.py", "asgi.py", "celery.py"] or
                    file.startswith("__")
                ):
                    continue
                    
                parts = rel_path.replace("\\", "/").split("/")
                if any(part in excluded_dirs for part in parts):
                    continue
                    
                candidate_files.append((file, rel_path))
                
        scored_files = []
        for file, rel_path in candidate_files:
            score = 0
            
            # Tiêu chí: Tên file / đường dẫn chứa từ khóa dương (+30 điểm)
            pos_keywords = ["service", "handler", "usecase", "use_case", "manager", "repository", "repo", "controller", "api", "core", "domain", "business", "logic", "processor", "worker", "command", "query"]
            if any(kw in rel_path.lower() for kw in pos_keywords):
                score += 30
                
            # Tiêu chí: Tên file chứa từ khóa âm (-50 điểm)
            neg_keywords = ["config", "settings", "constant", "enum", "schema", "migration", "seed", "fixture"]
            if any(kw in rel_path.lower() for kw in neg_keywords):
                score -= 50
                
            # Step 2: Score content
            abs_path = os.path.join(repo_path, rel_path)
            content_score = 0
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    
                if language == "python":
                    content_score = self._score_python_content(content)
                elif language == "java":
                    content_score = self._score_java_content(content)
            except Exception as e:
                logger.debug(f"Error reading/parsing file {rel_path}: {e}")
                content_score = 0
                
            score += content_score
            logger.debug(f"Score {score} — {rel_path}")
            scored_files.append((rel_path, score))
            
        # Step 3: Threshold decision
        results = [rel_path for rel_path, score in scored_files if score >= 40]
        if not results:
            results = [rel_path for rel_path, score in scored_files if score >= 20]
        if not results:
            results = [rel_path for file, rel_path in candidate_files]
            
        return results

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
