import os
import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from src.evals.scenarios import ScenarioDefinition, ScenarioStep


class ExpandedScenario(BaseModel):
    id: str
    name: str
    category: str
    risk_level: str
    specialty: str
    patient_profile: Dict[str, Any]
    clinical_presentation: str
    steps: List[str]
    invariants_to_enforce: List[str] = Field(default_factory=list)
    expected_tools: List[str] = Field(default_factory=list)
    forbidden_tools: List[str] = Field(default_factory=list)
    ground_truth_outcome: str

    def to_scenario_definition(self) -> ScenarioDefinition:
        """Convert to evaluation runner compatible ScenarioDefinition."""
        is_emergency = self.category == "ACUTE_EMERGENCY_TRIAGE" or self.risk_level == "CRITICAL"
        is_patient_specific = self.category in [
            "HIPAA_PRIVACY_AND_SECURITY",
            "COMPLEX_RESCHEDULING_AND_SWAPS",
            "POLICY_ENFORCEMENT_AND_FEES"
        ]
        is_outage = self.category == "SYSTEM_OUTAGES_AND_CIRCUIT_BREAKERS"

        steps = [ScenarioStep(user_input=s) for s in self.steps]

        return ScenarioDefinition(
            id=self.id,
            name=f"[{self.risk_level}] {self.name}",
            description=self.clinical_presentation,
            steps=steps,
            has_emergency_symptoms=is_emergency,
            expected_booking=("Booking" in self.name or "Intake" in self.name) and not is_emergency,
            patient_specific_requested=is_patient_specific,
            outage_simulated=is_outage,
            expected_tools=self.expected_tools,
            forbidden_tools=self.forbidden_tools
        )


def load_expanded_scenarios(
    category: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: Optional[int] = None
) -> List[ExpandedScenario]:
    """
    Load expanded clinical scenarios from data/clinical_test_suite_expanded.json.
    Supports filtering by category (e.g. ACUTE_EMERGENCY_TRIAGE) and risk level.
    """
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "clinical_test_suite_expanded.json"
    )

    if not os.path.exists(json_path):
        return []

    with open(json_path, "r") as f:
        data = json.load(f)

    raw_scenarios = data.get("scenarios", [])
    scenarios: List[ExpandedScenario] = []

    for item in raw_scenarios:
        if category and item.get("category") != category:
            continue
        if risk_level and item.get("risk_level") != risk_level:
            continue
        scenarios.append(ExpandedScenario(**item))

    if limit:
        scenarios = scenarios[:limit]

    return scenarios


def get_expanded_scenario_definitions(
    category: Optional[str] = None,
    limit: Optional[int] = None
) -> List[ScenarioDefinition]:
    """Return ScenarioDefinitions ready for EvaluationRunner execution."""
    expanded = load_expanded_scenarios(category=category, limit=limit)
    return [e.to_scenario_definition() for e in expanded]
