from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class FailureReport(BaseModel):
    """
    Standardized, decoupled failure object emitted by the evaluation harness
    when an invariant or rubric threshold is violated.
    Consumed by the Root-Cause Analyzer to generate evidence-driven patches.
    """
    failure_id: str
    scenario_id: str
    scenario_name: str
    failed_invariant_or_rubric: str
    severity: str  # "CRITICAL", "HIGH", "MEDIUM"
    relevant_turn: int
    observed_tool_calls: List[str] = Field(default_factory=list)
    expected_behavior: str
    actual_behavior: str
    root_cause: str
    missing_or_incorrect_action: str
    evidence_references: Dict[str, Any] = Field(default_factory=dict)
