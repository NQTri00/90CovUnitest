import json
import logging
from typing import Dict, Any

from agent.state import AgentState
from agent.llm.client import OpenRouterClient, clean_json_response
from agent.llm.prompts import STAGE5_SYSTEM_PROMPT, STAGE5_USER_PROMPT_TEMPLATE
from agent.progress import update_progress

logger = logging.getLogger(__name__)

class Stage5Correction:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_client = OpenRouterClient()
        self.model = config.get("models", {}).get("stage5", "kimi/kimi-k2.6")
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
        if not self.llm_client.api_key or self.llm_client.api_key.startswith("your-openrouter-api-key"):
            logger.error("OPENROUTER_API_KEY is unset or mock. Programmatic simulation fallback is disabled.")
            raise RuntimeError("Self-correction failed: OPENROUTER_API_KEY is not configured or mock.")
        else:
            try:
                user_prompt = STAGE5_USER_PROMPT_TEMPLATE.format(
                    test_plan_json=json.dumps(test_plan, indent=2),
                    coverage_report_json=json.dumps(coverage_report, indent=2)
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

                cleaned_response = clean_json_response(response)
                updated_plan = json.loads(cleaned_response)
            except Exception as e:
                logger.error(f"Stage 5 LLM correction failed: {e}.")
                raise RuntimeError(f"Self-correction LLM call failed: {e}")

        if updated_plan:
            state["test_plan"] = updated_plan

        state["history"].append(f"Self-correction loop retry #{new_retry_count} triggered.")
        update_progress(5, 60, f"Đã sinh kế hoạch kiểm thử mới nhằm tối ưu hóa độ bao phủ.")
        return state
