import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.stages.stage1_analysis import Stage1Analysis
from agent.stages.stage2_planning import Stage2Planning
from agent.stages.stage3_generation import Stage3Generation
from agent.stages.stage4_execution import Stage4Execution
from agent.stages.stage5_correction import Stage5Correction

logger = logging.getLogger(__name__)

def build_agent_graph(config: Dict[str, Any]) -> StateGraph:
    """
    Build and compile the LangGraph workflow for the Unit Test Agent.
    """
    # Instantiate stage handlers
    stage1 = Stage1Analysis(config)
    stage2 = Stage2Planning(config)
    stage3 = Stage3Generation(config)
    stage4 = Stage4Execution(config)
    stage5 = Stage5Correction(config)

    # Initialize graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("stage1_analysis", stage1.run)
    workflow.add_node("stage2_planning", stage2.run)
    workflow.add_node("stage3_generation", stage3.run)
    workflow.add_node("stage4_execution", stage4.run)
    workflow.add_node("stage5_correction", stage5.run)

    # Define simple edges
    workflow.set_entry_point("stage1_analysis")
    workflow.add_edge("stage1_analysis", "stage2_planning")
    workflow.add_edge("stage2_planning", "stage3_generation")
    workflow.add_edge("stage3_generation", "stage4_execution")
    workflow.add_edge("stage4_execution", "stage5_correction")

    # Define conditional routing for Stage 5 (Self-Correction Loop)
    def should_continue_loop(state: AgentState) -> str:
        coverage_report = state.get("coverage_report")
        test_plan = state.get("test_plan")
        
        if not coverage_report or not test_plan:
            return END

        current_coverage = coverage_report.get("total_coverage", 0.0)
        target_coverage = float(test_plan.get("target_coverage", 90.0))
        retry_count = state.get("retry_count", 0)
        max_retry = config.get("max_retry", 3)

        if current_coverage >= target_coverage or retry_count >= max_retry:
            logger.info("Feedback loop complete. Finalizing execution graph.")
            return END
            
        logger.info(f"Loop routing back to Stage 3 (attempt {retry_count}/{max_retry})")
        return "stage3_generation"

    workflow.add_conditional_edges(
        "stage5_correction",
        should_continue_loop,
        {
            "stage3_generation": "stage3_generation",
            END: END
        }
    )

    return workflow.compile()
