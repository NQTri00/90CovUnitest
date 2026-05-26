from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict):
    repo_path: str
    language: str
    framework: str
    service_files: List[str]
    analysis_result: Optional[Dict[str, Any]]
    test_plan: Optional[Dict[str, Any]]
    generated_tests: List[Dict[str, Any]]
    coverage_report: Optional[Dict[str, Any]]
    retry_count: int
    history: List[str]
