import os
import sys
import argparse
import yaml
import json
import logging
from agent.graph import build_agent_graph
from agent.state import AgentState

# Reconfigure stdout/stderr to use UTF-8 to prevent encoding errors on Windows
if sys.platform.startswith("win") and "pytest" not in sys.modules:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("unit_test_agent")

def load_config(config_path: str) -> dict:
    if not os.path.exists(config_path):
        logger.warning(f"Config file not found at {config_path}. Using default settings.")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def main():
    parser = argparse.ArgumentParser(description="Unit Test Agent - Tự động viết và đánh giá unit test")
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Đường dẫn cục bộ tới thư mục repository cần sinh test"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Đường dẫn tới file config.yaml"
    )
    parser.add_argument(
        "--files",
        type=str,
        nargs="*",
        help="Danh sách các file cụ thể cần sinh test (nếu chỉ muốn chạy trên file thay đổi)"
    )
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo)
    if not os.path.exists(repo_path):
        logger.error(f"Thư mục repository không tồn tại: {repo_path}")
        return

    logger.info(f"Khởi chạy Unit Test Agent cho repository: {repo_path}")

    # Load config
    config = load_config(args.config)

    # Build graph application
    app = build_agent_graph(config)

    # Get specific files if passed
    service_files = []
    if args.files:
        service_files = args.files

    # Prepare initial state
    initial_state = AgentState(
        repo_path=repo_path,
        language="",
        framework="",
        service_files=service_files,
        analysis_result=None,
        test_plan=None,
        generated_tests=[],
        coverage_report=None,
        retry_count=0,
        history=[]
    )

    logger.info("Bắt đầu thực thi pipeline LangGraph...")
    try:
        final_state = app.invoke(initial_state)
    except Exception as e:
        logger.critical(f"Lỗi hệ thống trong quá trình chạy pipeline: {e}", exc_info=True)
        return

    # Print logs and summary
    print("\n" + "=" * 50)
    print("NHẬT KÝ HOẠT ĐỘNG (HISTORY LOGS)")
    print("=" * 50)
    for log in final_state.get("history", []):
        print(f"- {log}")

    print("\n" + "=" * 50)
    print("KẾT QUẢ CUỐI CÙNG (FINAL SUMMARY)")
    print("=" * 50)
    
    # Save artifacts into the repo path
    if final_state.get("test_plan"):
        plan_out = os.path.join(repo_path, "test_plan.json")
        with open(plan_out, "w", encoding="utf-8") as pf:
            json.dump(final_state["test_plan"], pf, indent=2, ensure_ascii=False)
        print(f"Saved test plan to: {plan_out}")

    if final_state.get("coverage_report"):
        report = final_state["coverage_report"]
        report_out = os.path.join(repo_path, "coverage_report.json")
        with open(report_out, "w", encoding="utf-8") as rf:
            json.dump(report, rf, indent=2, ensure_ascii=False)
        print(f"Saved coverage report to: {report_out}")
        print(f"Overall Coverage: {report.get('total_coverage')}%")
        print(f"Tests Passed: {report.get('summary', {}).get('passed')}/{report.get('summary', {}).get('total_tests')}")

    print(f"Generated Test Files: {len(final_state.get('generated_tests', []))}")
    for gf in final_state.get("generated_tests", []):
        print(f"  - {gf['file_path']}")
    print("=" * 50)

if __name__ == "__main__":
    main()
