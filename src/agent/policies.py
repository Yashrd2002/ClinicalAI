import os
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


# -------------------------------------------------------------
# Tier 1: CORE_INVARIANTS (Immutable, Code-Enforced Guardrails)
# -------------------------------------------------------------
IMMUTABLE_CORE_INVARIANTS = {
    "INVARIANT_EMERGENCY_ROUTING": {
        "description": "If acute red flags are reported, routine scheduling is prohibited and escalate_emergency_triage must be invoked immediately.",
        "forbidden_tools_on_emergency": ["search_available_slots", "hold_appointment_slot", "confirm_booking", "reschedule_appointment"],
        "required_tool_on_emergency": "escalate_emergency_triage"
    },
    "INVARIANT_PHI_AUTHENTICATION": {
        "description": "Patient identity must be authenticated via 2 identifiers before slot holds, appointment listings, rescheduling, or cancellations.",
        "gated_tools": ["hold_appointment_slot", "confirm_booking", "get_patient_appointments", "reschedule_appointment", "cancel_appointment"]
    },
    "INVARIANT_EXPLICIT_CONFIRMATION": {
        "description": "Confirming, rescheduling, or cancelling appointments requires explicit confirmation from the patient.",
        "gated_tools": ["confirm_booking", "reschedule_appointment", "cancel_appointment"]
    },
    "INVARIANT_DB_STATE_CONSISTENCY": {
        "description": "Conversational claims must strictly match EHR database state (no hallucinated bookings)."
    }
}


# -------------------------------------------------------------
# Tier 2 & 3: TUNABLE_POLICIES & CONVERSATIONAL PREFERENCES
# -------------------------------------------------------------
class PolicyPatch(BaseModel):
    """
    Typed, schema-validated policy patch emitted by the Root-Cause Analyzer
    and closed-loop optimizer.
    """
    patch_id: str
    target_policy: str  # e.g. "triage_screening", "clarification_thresholds", "outage_recovery"
    trigger: str        # Condition that activates the rule
    rule: str           # The reinforced instruction or operational constraint
    required_actions: List[str] = Field(default_factory=list)
    forbidden_actions: List[str] = Field(default_factory=list)
    rationale: str
    source_failure_id: str
    severity: str = "CRITICAL"


class PolicyStore:
    """
    Manages active tunable clinical policies and conversational guidance.
    Allows sandboxed shadow evaluation and regression testing.
    """
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config", "clinical_policies.json"
        )
        self.tunable_policies: Dict[str, Any] = {}
        self.applied_patches: List[Dict[str, Any]] = []
        self.load_policies()

    def load_policies(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                data = json.load(f)
                self.tunable_policies = data.get("tunable_policies", {})
                self.applied_patches = data.get("applied_patches", [])
        else:
            # Baseline configuration (un-patched)
            self.tunable_policies = {
                "triage_screening": {
                    "enabled": False,  # Baseline agent starts without proactive pre-scheduling triage gate
                    "red_flag_keywords": ["chest pain", "shortness of breath", "trouble breathing", "loss of consciousness", "stroke", "severe hemorrhage"],
                    "pre_tool_triage_required": False
                },
                "ambiguity_handling": {
                    "ask_clarification_on_vague_dates": True,
                    "max_inferred_days": 1
                },
                "outage_resiliency": {
                    "explain_service_error": True,
                    "provide_clinic_phone": True,
                    "clinic_phone_number": "555-0100"
                }
            }
            self.applied_patches = []

    def save_policies(self, target_path: Optional[str] = None):
        path = target_path or self.config_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "tunable_policies": self.tunable_policies,
                "applied_patches": self.applied_patches
            }, f, indent=2)

    def apply_patch(self, patch: PolicyPatch) -> bool:
        """
        Apply a validated PolicyPatch to the tunable policy configuration.
        """
        # Ensure patch does not violate or try to override immutable core invariants
        if patch.target_policy in IMMUTABLE_CORE_INVARIANTS:
            raise ValueError(f"Cannot patch immutable core invariant '{patch.target_policy}'.")

        # Update specific tunable policy
        if patch.target_policy == "triage_screening":
            if "triage_screening" not in self.tunable_policies:
                self.tunable_policies["triage_screening"] = {}
            self.tunable_policies["triage_screening"]["enabled"] = True
            self.tunable_policies["triage_screening"]["pre_tool_triage_required"] = True
            self.tunable_policies["triage_screening"]["guidance"] = patch.rule
            self.tunable_policies["triage_screening"]["required_actions"] = patch.required_actions
            self.tunable_policies["triage_screening"]["forbidden_actions"] = patch.forbidden_actions

        self.applied_patches.append(patch.model_dump())
        return True

    def clone(self) -> 'PolicyStore':
        """Create an in-memory clone for shadow sandboxed evaluation."""
        cloned = PolicyStore(config_path="/tmp/non_existent_path.json")
        cloned.tunable_policies = json.loads(json.dumps(self.tunable_policies))
        cloned.applied_patches = list(self.applied_patches)
        return cloned

    def get_prompt_policy_instructions(self) -> str:
        """Generate dynamic policy prompt text based on currently active tunable policies."""
        instructions = []
        triage = self.tunable_policies.get("triage_screening", {})
        if triage.get("enabled"):
            instructions.append(
                "### CLINICAL TRIAGE SAFETY PROTOCOL (CRITICAL):\n"
                "- Before querying slots or discussing appointments, ALWAYS assess if the patient mentions acute, severe, or red-flag symptoms.\n"
                "- Red-flag symptoms include: crushing chest pain, difficulty breathing, sudden weakness/numbness, severe trauma.\n"
                "- If any acute symptom is reported, you MUST IMMEDIATELY call `escalate_emergency_triage`.\n"
                "- DO NOT search for routine slots, hold slots, or attempt to schedule an appointment for acute red-flag cases."
            )
        
        ambiguity = self.tunable_policies.get("ambiguity_handling", {})
        if ambiguity.get("ask_clarification_on_vague_dates"):
            instructions.append(
                "### CLARIFICATION PROTOCOL:\n"
                "- If the patient's request is ambiguous (e.g. 'sometime next week' or 'an appointment soon'), DO NOT guess a date or call booking tools immediately.\n"
                "- Ask the patient for their preferred days of the week, times of day, or specific dates before searching."
            )

        outage = self.tunable_policies.get("outage_resiliency", {})
        if outage.get("explain_service_error"):
            instructions.append(
                "### SYSTEM OUTAGE & ERROR PROTOCOL:\n"
                "- If any tool returns a service unavailable error (503) or technical failure, never fabricate appointments or invent availability.\n"
                "- Clearly inform the patient of the temporary technical issue and offer the clinic's phone number (555-0100) for immediate assistance."
            )

        return "\n\n".join(instructions)
