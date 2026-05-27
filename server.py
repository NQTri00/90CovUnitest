import os
import uuid
import logging
import threading
import contextvars
from typing import Dict, Any, List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Shared context variable & database from progress module
from agent.progress import current_run_id, runs_db

class RunLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

    def emit(self, record):
        try:
            run_id = current_run_id.get()
            if run_id and run_id in runs_db:
                log_entry = self.format(record)
                runs_db[run_id]["logs"].append(log_entry)
        except Exception:
            self.handleError(record)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logging.getLogger().addHandler(RunLogHandler())
logger = logging.getLogger("web_server")

app = FastAPI(title="Unit Test Agent Dashboard")

class RunRequest(BaseModel):
    repo_path: str

class ResumeRequest(BaseModel):
    selected_test_ids: List[str]

def run_agent_task(run_id: str, repo_path: str):
    import yaml
    from agent.stages.stage1_analysis import Stage1Analysis
    from agent.stages.stage2_planning import Stage2Planning
    from agent.progress import update_progress

    # Set contextvar for the background thread execution
    token = current_run_id.set(run_id)

    logger.info(f"Starting Phase 1 (Analysis & Planning) for run_id={run_id}, repo={repo_path}")
    try:
        abs_repo_path = os.path.abspath(repo_path)
        if not os.path.exists(abs_repo_path):
            raise ValueError(f"Path does not exist: {repo_path}")

        # Load config
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

        # Initialize State
        initial_state = {
            "repo_path": abs_repo_path,
            "language": "",
            "framework": "",
            "service_files": [],
            "analysis_result": {},
            "test_plan": {},
            "generated_tests": [],
            "coverage_report": {},
            "retry_count": 0,
            "history": []
        }

        # Run Stage 1: Analysis
        stage1 = Stage1Analysis(config)
        state_after_s1 = stage1.run(initial_state)

        # Run Stage 2: Planning
        stage2 = Stage2Planning(config)
        state_after_s2 = stage2.run(state_after_s1)

        # Save state and update database for human approval
        runs_db[run_id]["agent_state"] = state_after_s2
        runs_db[run_id]["status"] = "awaiting_user_approval"
        runs_db[run_id]["test_plan"] = state_after_s2.get("test_plan", {})
        runs_db[run_id]["history"] = state_after_s2.get("history", [])

        # Update progress to awaiting_user_approval status
        if "progress" in runs_db[run_id]:
            runs_db[run_id]["progress"]["status"] = "awaiting_user_approval"

        logger.info(f"Phase 1 completed for run_id={run_id}. Awaiting user selection of test cases.")

    except Exception as e:
        logger.error(f"Phase 1 failed for run_id={run_id}: {e}", exc_info=True)
        if run_id in runs_db:
            runs_db[run_id]["status"] = "failed"
            runs_db[run_id]["error"] = str(e)
    finally:
        current_run_id.reset(token)

def resume_agent_task(run_id: str, selected_test_ids: List[str]):
    import yaml
    from agent.stages.stage3_generation import Stage3Generation
    from agent.stages.stage4_execution import Stage4Execution
    from agent.stages.stage5_correction import Stage5Correction
    from agent.progress import update_progress

    token = current_run_id.set(run_id)

    logger.info(f"Resuming Phase 2 (Generation & Correction) for run_id={run_id}")
    try:
        # Load saved state
        state = runs_db[run_id].get("agent_state")
        if not state:
            raise ValueError("No saved agent state found for this run.")

        # Filter test plan to only include selected test cases
        test_plan = state.get("test_plan", {})
        all_cases = test_plan.get("test_cases", [])
        selected_cases = [tc for tc in all_cases if tc.get("test_id") in selected_test_ids]
        test_plan["test_cases"] = selected_cases
        state["test_plan"] = test_plan

        # Load config
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

        abs_repo_path = state["repo_path"]
        stage3 = Stage3Generation(config)
        stage4 = Stage4Execution(config)
        stage5 = Stage5Correction(config)

        # Loop Correction
        retry_count = 0
        max_retry = config.get("max_retry", 3)
        target_coverage = float(test_plan.get("target_coverage", 90.0))

        while True:
            # Stage 3
            state = stage3.run(state)
            # Stage 4
            state = stage4.run(state)
            
            # Check coverage
            coverage_report = state.get("coverage_report", {})
            current_coverage = coverage_report.get("total_coverage", 0.0)
            
            # Stage 5
            state = stage5.run(state)
            
            retry_count = state.get("retry_count", 0)
            if current_coverage >= target_coverage or retry_count >= max_retry:
                logger.info("Feedback loop complete or max retries reached. Finalizing Phase 2.")
                break
                
            logger.info(f"Loop routing back to Stage 3 (attempt {retry_count}/{max_retry})")
            update_progress(5, 80, f"Đang tối ưu độ bao phủ, quay lại Stage 3 (Lần {retry_count}/{max_retry})...")

        # Retrieve outputs and update database
        runs_db[run_id]["status"] = "completed"
        runs_db[run_id]["test_plan"] = state.get("test_plan", {})
        runs_db[run_id]["coverage_report"] = state.get("coverage_report", {})
        runs_db[run_id]["history"] = state.get("history", [])

        # Load generated test files content
        generated_files = []
        output_base_dir = os.path.join(abs_repo_path, "generated_tests")
        if os.path.exists(output_base_dir):
            for root, dirs, files in os.walk(output_base_dir):
                # Skip __pycache__ folders
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in files:
                    if f.endswith(".pyc") or f.startswith("."):
                        continue
                    file_abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(file_abs_path, abs_repo_path)
                    try:
                        with open(file_abs_path, "r", encoding="utf-8") as file_handle:
                            content = file_handle.read()
                        generated_files.append({
                            "path": rel_path,
                            "content": content
                        })
                    except Exception as fe:
                        logger.error(f"Failed to read generated test file {rel_path}: {fe}")

        runs_db[run_id]["generated_files"] = generated_files
        logger.info(f"Phase 2 execution completed successfully for run_id={run_id}")

    except Exception as e:
        logger.error(f"Phase 2 execution failed for run_id={run_id}: {e}", exc_info=True)
        if run_id in runs_db:
            runs_db[run_id]["status"] = "failed"
            runs_db[run_id]["error"] = str(e)
    finally:
        current_run_id.reset(token)

@app.post("/api/run")
def start_run(req: RunRequest, background_tasks: BackgroundTasks):
    # Check path existence first
    abs_path = os.path.abspath(req.repo_path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=400, detail=f"Thư mục '{req.repo_path}' không tồn tại trên hệ thống.")

    run_id = str(uuid.uuid4())
    runs_db[run_id] = {
        "run_id": run_id,
        "repo_path": req.repo_path,
        "status": "running",
        "logs": [],
        "test_plan": {},
        "coverage_report": {},
        "history": [],
        "generated_files": [],
        "progress": {
            "stage": 1,
            "percentage": 0,
            "message": "Đang chuẩn bị tác vụ...",
            "status": "running",
            "stage_data": {}
        },
        "error": None
    }
    
    # Start task in background thread
    background_tasks.add_task(run_agent_task, run_id, req.repo_path)
    return {"run_id": run_id, "status": "running"}

@app.post("/api/resume/{run_id}")
def resume_run(run_id: str, req: ResumeRequest, background_tasks: BackgroundTasks):
    if run_id not in runs_db:
        raise HTTPException(status_code=404, detail="Run ID not found")
        
    if runs_db[run_id]["status"] != "awaiting_user_approval":
        raise HTTPException(status_code=400, detail="Run is not awaiting user approval")

    runs_db[run_id]["status"] = "running"
    runs_db[run_id]["error"] = None
    runs_db[run_id]["progress"] = {
        "stage": 3,
        "percentage": 0,
        "message": "Bắt đầu sinh mã kiểm thử từ các kịch bản đã chọn...",
        "status": "running",
        "stage_data": {}
    }
    
    background_tasks.add_task(resume_agent_task, run_id, req.selected_test_ids)
    return {"run_id": run_id, "status": "running"}

@app.get("/api/status/{run_id}")
def get_status(run_id: str):
    if run_id not in runs_db:
        raise HTTPException(status_code=404, detail="Run ID not found")
    return runs_db[run_id]

@app.get("/api/runs")
def get_runs():
    return [
        {
            "run_id": rid,
            "repo_path": data["repo_path"],
            "status": data["status"],
            "error": data["error"]
        }
        for rid, data in runs_db.items()
    ]

@app.get("/api/list-dirs")
def list_directories(path: str = "."):
    try:
        base_dir = "/app"
        target_path = os.path.abspath(os.path.join(base_dir, path))
        if not target_path.startswith(base_dir):
            target_path = base_dir

        if not os.path.exists(target_path):
            return {"current_path": "", "directories": []}

        subdirs = []
        for d in os.listdir(target_path):
            full_d = os.path.join(target_path, d)
            if os.path.isdir(full_d) and not d.startswith(".") and d not in ["venv", ".venv", "node_modules", "static", "agent", "schemas", "tests", "__pycache__", ".git", ".github", ".pytest_cache"]:
                subdirs.append(d)

        rel_path = os.path.relpath(target_path, base_dir)
        if rel_path == ".":
            rel_path = ""

        return {
            "current_path": rel_path.replace("\\", "/"),
            "directories": sorted(subdirs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve static files
os.makedirs("static", exist_ok=True)

@app.get("/")
def read_index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
