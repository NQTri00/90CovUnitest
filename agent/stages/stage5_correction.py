import os
import json
import logging
from typing import Dict, Any, List, Optional

from agent.state import AgentState
from agent.llm.client import OpenRouterClient, clean_json_response
from agent.llm.prompts import STAGE5_SYSTEM_PROMPT, STAGE5_USER_PROMPT_TEMPLATE
from agent.progress import update_progress

logger = logging.getLogger(__name__)

class Stage5Correction:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_client = OpenRouterClient()
        self.model = config.get("models", {}).get("stage5", "deepseek/deepseek-v4-flash")
        self.max_retry = config.get("max_retry", 3)

    def run(self, state: AgentState) -> AgentState:
        """
        Run Stage 5: Self-Correction (Feedback Loop).
        """
        coverage_report = state.get("coverage_report")
        test_plan = state.get("test_plan")

        if not coverage_report or not test_plan:
            raise ValueError("Missing coverage report or test plan in state.")

        current_coverage = coverage_report.get("total_coverage", 0.0)
        target_coverage = float(test_plan.get("target_coverage", 90.0))
        retry_count = state.get("retry_count", 0)

        logger.info(f"Checking coverage target: current={current_coverage}%, target={target_coverage}% (retry={retry_count}/{self.max_retry})")
        update_progress(5, 10, f"Kiểm tra mục tiêu độ bao phủ ({current_coverage}%/{target_coverage}%)...")

        # Base case 1: Target coverage met
        if current_coverage >= target_coverage:
            logger.info("Target coverage met. Self-correction succeeded!")
            state["history"].append("Self-correction loop finished: Target coverage achieved.")
            update_progress(5, 100, f"Độ bao phủ đạt yêu cầu ({current_coverage}%). Kết thúc vòng sửa lỗi.")
            return state

        # Base case 2: Max retries exceeded
        if retry_count >= self.max_retry:
            logger.warning("Max retries exceeded. Terminating feedback loop without meeting target coverage.")
            state["history"].append("Self-correction loop finished: Max retry limit reached.")
            update_progress(5, 100, f"Đạt giới hạn số lần sửa đổi tối đa ({self.max_retry}). Kết thúc.")
            return state

        # Trigger self-correction retry
        new_retry_count = retry_count + 1
        state["retry_count"] = new_retry_count
        logger.info(f"Coverage not met. Triggering self-correction loop (attempt {new_retry_count}/{self.max_retry}).")
        update_progress(5, 30, f"Độ bao phủ chưa đạt {target_coverage}%. Bắt đầu tự động sửa đổi lần {new_retry_count}/{self.max_retry}...")

        # Perform correction (LLM or fallback)
        updated_plan = None
        MOCK_KEY_PREFIXES = ("your-openrouter-api-key", "mock-key", "sk-test", "test-")
        is_mock_key = not self.llm_client.api_key or any(self.llm_client.api_key.startswith(p) for p in MOCK_KEY_PREFIXES)
        if is_mock_key:
            logger.error("OPENROUTER_API_KEY is unset or mock. Programmatic simulation fallback is disabled.")
            raise RuntimeError("Self-correction failed: OPENROUTER_API_KEY is not configured or mock.")
        else:
            try:
                # Extract uncovered sources context
                uncovered_sources = {}
                for class_name, class_data in coverage_report.get("classes", {}).items():
                    if class_data.get("uncovered_lines"):
                        source_snippet = self._extract_uncovered_snippets(
                            state, class_name, class_data["uncovered_lines"]
                        )
                        if source_snippet:
                            uncovered_sources[class_name] = source_snippet
                
                # Format uncovered sources context
                uncovered_context_str = ""
                if uncovered_sources:
                    for class_name, snippet in uncovered_sources.items():
                        uncovered_context_str += f"Class {class_name}:\n```\n{snippet}\n```\n\n"
                else:
                    uncovered_context_str = "Không có thông tin chi tiết hoặc không tìm thấy file nguồn."

                user_prompt = STAGE5_USER_PROMPT_TEMPLATE.format(
                    test_plan_json=json.dumps(test_plan, indent=2),
                    coverage_report_json=json.dumps(coverage_report, indent=2),
                    uncovered_sources_context=uncovered_context_str
                )

                messages = [
                    {"role": "system", "content": STAGE5_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]

                response = self.llm_client.chat_completion(
                    messages=messages,
                    model=self.model,
                    response_format={"type": "json_object"}
                )

                from agent.llm.client import robust_json_loads
                cleaned_response = clean_json_response(response)
                updated_plan = robust_json_loads(cleaned_response)
            except Exception as e:
                logger.error(f"Stage 5 LLM correction failed: {e}.")
                raise RuntimeError(f"Self-correction LLM call failed: {e}")

        if updated_plan:
            state["test_plan"] = updated_plan

        state["history"].append(f"Self-correction loop retry #{new_retry_count} triggered.")
        update_progress(5, 60, f"Đã sinh kế hoạch kiểm thử mới nhằm tối ưu hóa độ bao phủ.")
        return state

    def _extract_uncovered_snippets(self, state: AgentState, class_name: str, uncovered_lines: List[int]) -> Optional[str]:
        """
        Extract code snippets around uncovered lines from the source file.
        """
        analysis_result = state.get("analysis_result", {})
        services = analysis_result.get("services", [])
        file_path = None
        for s in services:
            if s.get("class_name") == class_name:
                file_path = s.get("file_path")
                break
        
        if not file_path:
            for s in services:
                if s.get("class_name", "").lower() == class_name.lower():
                    file_path = s.get("file_path")
                    break

        if not file_path:
            return None

        repo_path = state.get("repo_path")
        abs_path = os.path.join(repo_path, file_path)
        if not os.path.exists(abs_path):
            return None

        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"Failed to read source file for snippet extraction {file_path}: {e}")
            return None

        snippet_lines = []
        num_lines = len(lines)
        visited = set()
        for u_line in sorted(uncovered_lines):
            idx = u_line - 1
            if idx < 0 or idx >= num_lines:
                continue
            
            start = max(0, idx - 3)
            end = min(num_lines, idx + 4)
            for i in range(start, end):
                if i not in visited:
                    visited.add(i)
                    prefix = ">>>" if (i + 1) in uncovered_lines else "   "
                    snippet_lines.append(f"{prefix} {i+1}: {lines[i].rstrip()}")
        
        if snippet_lines:
            return "\n".join(snippet_lines)
        return None
