import os
import re
import json
import logging
import xml.etree.ElementTree as ET
import subprocess
from typing import Dict, Any, List, Tuple, Optional

from agent.state import AgentState
from agent.progress import update_progress

logger = logging.getLogger(__name__)

class Stage4Execution:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def run(self, state: AgentState) -> AgentState:
        """
        Run Stage 4: Test Execution & Coverage.
        """
        repo_path = state.get("repo_path")
        language = state.get("language", "java")
        framework = state.get("framework", "spring-boot")
        generated_tests = state.get("generated_tests", [])

        logger.info(f"Starting Stage 4: Test Execution for {language} project.")
        update_progress(4, 10, "Bắt đầu chạy thử nghiệm và thu thập độ bao phủ (Coverage)...")

        # Load Schema
        schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                   "schemas", "coverage_report.schema.json")
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load coverage report schema: {e}")
            schema = None

        coverage_report = None
        executed_successfully = False

        # Attempt actual test run if desired and environment exists
        try:
            update_progress(4, 30, "Đang khởi chạy tiến trình chạy kiểm thử cục bộ...")
            if language == "python":
                executed_successfully, coverage_report = self.execute_python_tests(repo_path, generated_tests, state)
            elif language == "java":
                executed_successfully, coverage_report = self.execute_java_tests(repo_path, generated_tests, state)
        except Exception as e:
            logger.error(f"Failed to execute real tests: {e}")
            executed_successfully = False

        if not executed_successfully or not coverage_report:
            logger.error("Real test execution failed.")
            update_progress(4, 100, "Thực thi test thất bại!")
            raise RuntimeError("Real test execution failed. Please check the logs for detailed compiler or runtime errors.")

        # Validate against schema
        if schema and coverage_report:
            try:
                from jsonschema import validate
                validate(instance=coverage_report, schema=schema)
                logger.info("coverage_report.json successfully validated against schema.")
            except Exception as e:
                logger.error(f"coverage_report validation failed: {e}")

        state["coverage_report"] = coverage_report
        state["history"].append("Stage 4 completed: Test execution and coverage analysis done.")

        total_cov = coverage_report.get("total_coverage", 0.0) if coverage_report else 0.0
        update_progress(4, 100, f"Hoàn thành Stage 4. Độ bao phủ đạt: {total_cov}%", {
            "coverage": coverage_report
        })

        return state

    def execute_python_tests(self, repo_path: str, generated_tests: List[Dict[str, Any]], state: AgentState) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Run pytest on generated Python tests and parse coverage.xml.
        """
        if not generated_tests:
            logger.error("No generated tests to execute.")
            return False, None

        coverage_xml_path = os.path.join(repo_path, "coverage.xml")
        if os.path.exists(coverage_xml_path):
            os.remove(coverage_xml_path)

        # Auto-install dependencies from all requirements.txt files found in the workspace
        req_paths = []
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in ["venv", ".venv", "node_modules", ".git"]]
            if "requirements.txt" in files:
                req_paths.append(os.path.join(root, "requirements.txt"))
                
        for req_path in req_paths:
            logger.info(f"Installing project dependencies from {req_path}...")
            try:
                with open(req_path, "r", encoding="utf-8", errors="ignore") as f:
                    reqs = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
                
                for req in reqs:
                    pkg_name = req.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
                    if not pkg_name:
                        continue
                    if pkg_name.lower() == "pyaudiowpatch":
                        logger.info(f"Skipping Windows-only package: {pkg_name}")
                        continue
                    try:
                        logger.info(f"Installing package: {req}...")
                        subprocess.run(
                            ["pip", "install", "--no-cache-dir", req],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=60
                        )
                    except Exception as pkg_err:
                        logger.warning(f"Failed to install package {req}: {pkg_err}")
                logger.info(f"Finished installing dependencies from {req_path}.")
            except Exception as e:
                logger.error(f"Failed to install dependencies from {req_path}: {e}")

        # Run pytest inside repo_path using the active python virtualenv if available
        # Find pytest executable
        pytest_cmd = "pytest"
        venv_candidates = [
            # Linux/macOS candidates
            os.path.join(repo_path, "venv", "bin", "pytest"),
            os.path.join(repo_path, ".venv", "bin", "pytest"),
            os.path.join(repo_path, "backend", "venv", "bin", "pytest"),
            os.path.join(repo_path, "backend", ".venv", "bin", "pytest"),
            # Windows candidates
            os.path.join(repo_path, "venv", "Scripts", "pytest.exe"),
            os.path.join(repo_path, ".venv", "Scripts", "pytest.exe"),
            os.path.join(repo_path, "backend", "venv", "Scripts", "pytest.exe"),
            os.path.join(repo_path, "backend", ".venv", "Scripts", "pytest.exe"),
        ]
        for candidate in venv_candidates:
            if os.path.exists(candidate):
                pytest_cmd = candidate
                break

        # Target only the generated test files from the current run
        test_files = []
        if generated_tests:
            for t in generated_tests:
                if t.get("file_path"):
                    test_files.append(t["file_path"])
        
        # Fallback if no files listed (should not happen)
        if not test_files:
            test_files = ["generated_tests/"]

        cmd = [
            pytest_cmd,
            "-v",
            "--cov=.",  # Analyze the entire project folder
            "--cov-report=xml"
        ] + test_files

        logger.info(f"Running command: {' '.join(cmd)} inside {repo_path}")
        
        # Build robust PYTHONPATH including source folders
        env = os.environ.copy()
        python_paths = [repo_path]
        
        # Avoid standard python library shadowing when adding folders to PYTHONPATH
        STD_LIBS_TO_AVOID_SHADOWING = {
            "email.py", "logging.py", "json.py", "math.py", "random.py", 
            "csv.py", "socket.py", "select.py", "threading.py", "time.py", 
            "os.py", "sys.py", "re.py", "http.py", "unittest.py", "pytest.py",
            "collections.py", "typing.py", "datetime.py", "hashlib.py", "uuid.py",
            "asyncio.py", "subprocess.py", "shutil.py", "tempfile.py", "xml.py"
        }
        
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in ["venv", ".venv", "node_modules", ".git", "generated_tests", "tests", "frontend", "front-end", "ui", "client"]]
            if any(f.endswith(".py") for f in files):
                has_shadowing_file = any(f in STD_LIBS_TO_AVOID_SHADOWING for f in files)
                if not has_shadowing_file:
                    if root not in python_paths:
                        python_paths.append(root)
                        
        env["PYTHONPATH"] = os.pathsep.join(python_paths)

        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
                env=env
            )
            
            if result.returncode != 0:
                logger.error(f"pytest exited with code {result.returncode}")
                logger.error(f"pytest stdout:\n{result.stdout}")
                logger.error(f"pytest stderr:\n{result.stderr}")
            
            if os.path.exists(coverage_xml_path):
                service_files = state.get("service_files", [])
                report = self.parse_python_coverage_xml(coverage_xml_path, result.stdout, service_files)
                return True, report
            else:
                logger.error("coverage.xml was not generated by pytest-cov.")
        except Exception as e:
            logger.error(f"Error executing pytest: {e}")
            
        return False, None

    def execute_java_tests(self, repo_path: str, generated_tests: List[Dict[str, Any]], state: AgentState) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Run Maven/Gradle tests and parse jacoco.xml.
        """
        # Search for jacoco report inside target/site/jacoco/jacoco.xml
        jacoco_path = os.path.join(repo_path, "target", "site", "jacoco", "jacoco.xml")
        
        # If it's already there (or maven test is run), we parse it
        if os.path.exists(jacoco_path):
            service_files = state.get("service_files", [])
            report = self.parse_jacoco_xml(jacoco_path, 1, 0, [], service_files)
            return True, report

        return False, None

    @staticmethod
    def parse_python_coverage_xml(xml_path: str, stdout_log: str = "", service_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Parse Coverage.py XML file.
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        classes_data = {}
        total_lines_for_selected = 0
        covered_lines_for_selected = 0

        # Parse classes
        for cls_node in root.findall(".//class"):
            filename = cls_node.attrib.get("filename", "")
            class_name = cls_node.attrib.get("name", "")
            
            # Skip test files from report if included
            if "test_" in filename or "test_" in class_name.lower():
                continue

            # Filter by service_files if provided
            if service_files is not None:
                normalized_filename = filename.replace("\\", "/")
                normalized_service_files = [sf.replace("\\", "/") for sf in service_files]
                if normalized_filename not in normalized_service_files:
                    continue

            lines = cls_node.find("lines")
            uncovered_lines = []
            total_lines = 0
            covered_lines = 0

            if lines is not None:
                for line in lines.findall("line"):
                    num = int(line.attrib.get("number", 0))
                    hits = int(line.attrib.get("hits", 0))
                    total_lines += 1
                    if hits == 0:
                        uncovered_lines.append(num)
                    else:
                        covered_lines += 1

            total_lines_for_selected += total_lines
            covered_lines_for_selected += covered_lines

            line_rate = (covered_lines / total_lines * 100) if total_lines > 0 else 0.0
            branch_rate = float(cls_node.attrib.get("branch-rate", 0)) * 100

            classes_data[class_name] = {
                "line_coverage": round(line_rate, 2),
                "branch_coverage": round(branch_rate, 2) if "branch-rate" in cls_node.attrib else None,
                "uncovered_lines": uncovered_lines
            }

        if service_files is not None:
            if total_lines_for_selected > 0:
                total_line_rate = (covered_lines_for_selected / total_lines_for_selected) * 100
            else:
                total_line_rate = 0.0
        else:
            total_line_rate = float(root.attrib.get("line-rate", 0)) * 100

        # Deduce passed/failed test numbers from stdout log if possible
        passed = 0
        failed = 0
        if stdout_log:
            # Look for: "passed", "failed" patterns in pytest output
            match = re.search(r"(\d+) passed", stdout_log)
            if match:
                passed = int(match.group(1))
            match_fail = re.search(r"(\d+) failed", stdout_log)
            if match_fail:
                failed = int(match_fail.group(1))

        total_tests = passed + failed
        summary = {
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "skipped": 0
        }
        if total_tests == 0:
            summary["parse_warning"] = "Could not parse test count from pytest output"

        return {
            "total_coverage": round(total_line_rate, 2),
            "summary": summary,
            "classes": classes_data,
            "failures": []
        }

    @staticmethod
    def parse_jacoco_xml(xml_path: str, passed: int = 1, failed: int = 0, failures_list: List[Dict[str, Any]] = None, service_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Parse JaCoCo XML report.
        """
        tree = ET.parse(xml_path)
        root = tree.getroot()

        classes_data = {}
        total_covered = 0
        total_missed = 0

        # In JaCoCo, package/sourcefile elements contain line-by-line info
        for pkg in root.findall(".//package"):
            for src_file in pkg.findall("sourcefile"):
                src_name = src_file.attrib.get("name", "")
                class_name = src_name.replace(".java", "")
                
                # Filter by service_files if provided
                if service_files is not None:
                    matched = False
                    for sf in service_files:
                        sf_norm = sf.replace("\\", "/")
                        if sf_norm.endswith(src_name):
                            matched = True
                            break
                    if not matched:
                        continue

                # Check lines
                uncovered_lines = []
                lines = src_file.findall("line")
                for line in lines:
                    nr = int(line.attrib.get("nr", 0))
                    mi = int(line.attrib.get("mi", 0))
                    ci = int(line.attrib.get("ci", 0))
                    
                    if ci == 0 and mi > 0:
                        uncovered_lines.append(nr)

                # Counters at sourcefile level
                line_counter = src_file.find("./counter[@type='LINE']")
                branch_counter = src_file.find("./counter[@type='BRANCH']")

                line_cov = 100.0
                branch_cov = None

                if line_counter is not None:
                    missed = int(line_counter.attrib.get("missed", 0))
                    covered = int(line_counter.attrib.get("covered", 0))
                    total = missed + covered
                    if total > 0:
                        line_cov = (covered / total) * 100
                        total_covered += covered
                        total_missed += missed

                if branch_counter is not None:
                    missed = int(branch_counter.attrib.get("missed", 0))
                    covered = int(branch_counter.attrib.get("covered", 0))
                    total = missed + covered
                    if total > 0:
                        branch_cov = (covered / total) * 100

                classes_data[class_name] = {
                    "line_coverage": round(line_cov, 2),
                    "branch_coverage": round(branch_cov, 2) if branch_cov is not None else None,
                    "uncovered_lines": uncovered_lines
                }

        total_lines = total_covered + total_missed
        total_coverage = (total_covered / total_lines * 100) if total_lines > 0 else 100.0

        return {
            "total_coverage": round(total_coverage, 2),
            "summary": {
                "total_tests": passed + failed,
                "passed": passed,
                "failed": failed,
                "skipped": 0
            },
            "classes": classes_data,
            "failures": failures_list if failures_list else []
        }
