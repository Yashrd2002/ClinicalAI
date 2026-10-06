from typing import Tuple, Optional
from src.agent.policies import PolicyPatch, IMMUTABLE_CORE_INVARIANTS


class PolicyPatchValidator:
    """
    Two-tier patch validator:
    1. Schema validation (Pydantic types, non-empty fields, valid action sets).
    2. Safety & Immutable Invariant validation (prevents optimizer from weakening or bypassing core invariants).
    """
    VALID_TOOLS = {
        "escalate_emergency_triage",
        "verify_patient_identity",
        "search_available_slots",
        "hold_appointment_slot",
        "confirm_booking",
        "get_patient_appointments",
        "reschedule_appointment",
        "cancel_appointment"
    }

    def validate(self, patch: PolicyPatch) -> Tuple[bool, Optional[str]]:
        # 1. Check for attempts to tamper with immutable core invariants
        if patch.target_policy in IMMUTABLE_CORE_INVARIANTS:
            return False, f"ILLEGAL OPERATION: Target policy '{patch.target_policy}' is an immutable core invariant and cannot be modified."

        # 2. Check for empty fields
        if not patch.rule or len(patch.rule.strip()) < 10:
            return False, "SCHEMA ERROR: Rule statement must be meaningful and non-empty (minimum 10 characters)."

        if not patch.trigger or len(patch.trigger.strip()) < 5:
            return False, "SCHEMA ERROR: Trigger condition must be non-empty."

        # 3. Check tool names
        for action in patch.required_actions:
            if action not in self.VALID_TOOLS:
                return False, f"TOOL ERROR: Required action '{action}' is not a recognized EHR tool."

        for action in patch.forbidden_actions:
            if action not in self.VALID_TOOLS:
                return False, f"TOOL ERROR: Forbidden action '{action}' is not a recognized EHR tool."

        # 4. Check contradictory actions
        overlap = set(patch.required_actions).intersection(set(patch.forbidden_actions))
        if overlap:
            return False, f"CONTRADICTION ERROR: Actions {overlap} cannot be both required and forbidden simultaneously."

        return True, None
