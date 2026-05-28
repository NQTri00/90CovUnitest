import contextvars
from typing import Dict, Any

# Shared context variable for the run ID in current thread context
current_run_id = contextvars.ContextVar("current_run_id", default=None)

# Global in-memory reference to runs_db, initialized by server.py at startup
runs_db: Dict[str, Dict[str, Any]] = {}

def update_progress(stage: int, percentage: int, message: str, stage_data: Dict[str, Any] = None):
    """
    Thread-safe progress updates to runs_db using contextvars.
    """
    run_id = current_run_id.get()
    if run_id and run_id in runs_db:
        run_data = runs_db[run_id]
        
        # Ensure progress dictionary exists
        if "progress" not in run_data or not isinstance(run_data["progress"], dict):
            run_data["progress"] = {}
            
        progress = run_data["progress"]
        progress["stage"] = stage
        progress["percentage"] = percentage
        progress["message"] = message
        
        if stage_data is not None:
            if "stage_data" not in progress or not isinstance(progress["stage_data"], dict):
                progress["stage_data"] = {}
            progress["stage_data"].update(stage_data)
        else:
            if "stage_data" not in progress:
                progress["stage_data"] = {}
