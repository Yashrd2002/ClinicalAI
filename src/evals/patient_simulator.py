from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from src.ehr.database import EHRDatabase
from src.agent.dialogue_manager import DialogueManager
from src.evals.scenarios import ScenarioDefinition, ScenarioStep


class SimulationRunResult(BaseModel):
    scenario_id: str
    scenario_name: str
    turns_completed: int
    transcript: List[Dict[str, Any]]
    executed_tools: List[str]
    audit_log_entries: List[Dict[str, Any]]
    state_snapshot: Dict[str, Any]


class PatientSimulator:
    """
    Simulates multi-turn patient interaction according to scenario specifications,
    triggering realistic environment shifts (concurrent slot booking, service outages)
    at specified conversational turns.
    """
    def __init__(self, db: EHRDatabase, dialogue_manager: DialogueManager):
        self.db = db
        self.dm = dialogue_manager

    def run_scenario(self, scenario: ScenarioDefinition) -> SimulationRunResult:
        # Reset DB and agent state for deterministic execution
        self.db.seed_database()
        self.dm.reset_state()

        transcript = []

        for idx, step in enumerate(scenario.steps):
            # Apply pre-step environment hooks
            if step.pre_step_hook == "SIMULATE_SLOT_TAKEN":
                self.db.simulate_slot_taken("SLOT-102")
            elif step.pre_step_hook == "SIMULATE_OUTAGE":
                self.db.set_service_outage("search_available_slots", True)

            # Process user turn
            agent_reply = self.dm.process_turn(step.user_input)
            transcript.append({
                "turn": idx + 1,
                "user": step.user_input,
                "agent": agent_reply
            })

        return SimulationRunResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            turns_completed=len(scenario.steps),
            transcript=transcript,
            executed_tools=list(self.dm.state.executed_tools_history),
            audit_log_entries=[e.model_dump() for e in self.db.audit_log],
            state_snapshot=self.dm.state.model_dump()
        )
