import uuid
from typing import Optional
from src.optimizer.failure_object import FailureReport
from src.agent.policies import PolicyPatch


class RootCauseAnalyzer:
    """
    Evidence-driven diagnostic engine that inspects FailureReport objects
    and formulates structured, schema-compliant PolicyPatches.
    """
    def diagnose_and_propose(self, failure: FailureReport) -> PolicyPatch:
        """
        Derive targeted PolicyPatch directly from failure evidence, observed actions,
        and violated invariants.
        """
        inv = failure.failed_invariant_or_rubric
        
        # 1. Emergency routing invariant breach
        if inv == "INVARIANT_EMERGENCY_ROUTING":
            return PolicyPatch(
                patch_id=f"PATCH-TRIAGE-{uuid.uuid4().hex[:6].upper()}",
                target_policy="triage_screening",
                trigger="Patient presentation contains acute, severe, or potentially life-threatening red-flag symptoms (e.g. crushing chest pain, severe shortness of breath, sudden neurological deficits).",
                rule=(
                    "PRIORITY SAFETY DIRECTIVE: Prior to any slot searching, intake inquiry, or routine scheduling action, "
                    "screen for acute red-flag symptoms. If acute symptoms are detected, IMMEDIATELY halt routine scheduling flow "
                    "and execute `escalate_emergency_triage`. Instruct patient to call 911 or go to the nearest emergency department."
                ),
                required_actions=["escalate_emergency_triage"],
                forbidden_actions=["search_available_slots", "hold_appointment_slot", "confirm_booking", "reschedule_appointment"],
                rationale=(
                    f"Failure diagnosis from {failure.failure_id}: Agent executed routine scheduling tools "
                    f"({failure.observed_tool_calls}) when presenting complaint indicated an acute medical emergency."
                ),
                source_failure_id=failure.failure_id,
                severity=failure.severity
            )

        # 2. PHI authentication invariant breach
        elif inv == "INVARIANT_PHI_AUTHENTICATION":
            return PolicyPatch(
                patch_id=f"PATCH-PHI-{uuid.uuid4().hex[:6].upper()}",
                target_policy="phi_authentication_gate",
                trigger="Patient or caller requests access to appointment details, schedule modifications, or cancellations.",
                rule=(
                    "MANDATORY IDENTITY VERIFICATION: Two identifiers (Legal First + Last Name AND DOB or Phone) "
                    "must be authenticated via `verify_patient_identity` before disclosing existing appointments or executing holds/cancellations."
                ),
                required_actions=["verify_patient_identity"],
                forbidden_actions=["get_patient_appointments", "confirm_booking", "reschedule_appointment", "cancel_appointment"],
                rationale=f"Diagnosed from {failure.failure_id}: Unauthenticated tool calls observed.",
                source_failure_id=failure.failure_id,
                severity=failure.severity
            )

        # 3. Database state parity breach
        elif inv == "INVARIANT_DB_STATE_CONSISTENCY":
            return PolicyPatch(
                patch_id=f"PATCH-PARITY-{uuid.uuid4().hex[:6].upper()}",
                target_policy="confirmation_grounding",
                trigger="Agent communicates appointment confirmation or schedule modification to patient.",
                rule=(
                    "STATE GROUNDING DIRECTIVE: Never state or imply that an appointment is booked or modified "
                    "unless `confirm_booking` or `reschedule_appointment` returns success=True with confirmed appointment ID."
                ),
                required_actions=["confirm_booking"],
                forbidden_actions=[],
                rationale=f"Diagnosed from {failure.failure_id}: Agent claimed confirmed booking without matching EHR DB state.",
                source_failure_id=failure.failure_id,
                severity=failure.severity
            )

        # Fallback general patch
        else:
            return PolicyPatch(
                patch_id=f"PATCH-GEN-{uuid.uuid4().hex[:6].upper()}",
                target_policy="general_operational_guidance",
                trigger=f"Condition triggering {failure.failed_invariant_or_rubric}",
                rule=f"Execute required action {failure.missing_or_incorrect_action} and avoid safety violations.",
                required_actions=[failure.missing_or_incorrect_action] if failure.missing_or_incorrect_action != "N/A" else [],
                forbidden_actions=[],
                rationale=f"Diagnosed from {failure.failure_id}: {failure.root_cause}",
                source_failure_id=failure.failure_id,
                severity=failure.severity
            )
