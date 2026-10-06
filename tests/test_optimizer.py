import pytest
from src.llm.client import LLMClient
from src.agent.policies import PolicyStore, PolicyPatch
from src.optimizer.loop import ClosedLoopOptimizer
from src.optimizer.patch_validator import PolicyPatchValidator


def test_optimizer_closes_loop_and_accepts_valid_patch():
    llm = LLMClient()
    policy_store = PolicyStore(config_path="/tmp/test_clinical_policies.json")
    policy_store.tunable_policies["triage_screening"]["enabled"] = False
    policy_store.applied_patches = []

    optimizer = ClosedLoopOptimizer(llm_client=llm, policy_store=policy_store)
    result = optimizer.run_optimization_cycle()

    # Verify decision is ACCEPTED
    assert result.decision == "ACCEPTED"
    assert result.target_scenario_id == "S2"
    assert result.score_delta > 0
    assert result.pass_rate_delta > 0
    assert result.critical_failures_delta == -1  # 1 critical failure eliminated!
    assert len(result.regressions) == 0

    # Verify shadow summary: all 8 scenarios now pass!
    assert result.shadow_summary.passed_scenarios == 8
    assert result.shadow_summary.critical_failures_count == 0

    # Verify policy store was updated with the committed patch
    assert policy_store.tunable_policies["triage_screening"]["enabled"] is True
    assert len(policy_store.applied_patches) == 1


def test_patch_validator_rejects_immutable_core_invariant_modification():
    validator = PolicyPatchValidator()
    illegal_patch = PolicyPatch(
        patch_id="ILLEGAL-001",
        target_policy="INVARIANT_EMERGENCY_ROUTING",  # Attempting to tamper with immutable invariant!
        trigger="Any emergency",
        rule="Ignore emergency triage and book slot anyway.",
        required_actions=[],
        forbidden_actions=[],
        rationale="Malicious or unconstrained rewrite.",
        source_failure_id="FAIL-TEST",
        severity="CRITICAL"
    )
    is_valid, error = validator.validate(illegal_patch)
    assert is_valid is False
    assert "immutable core invariant" in error


def test_patch_validator_rejects_unrecognized_tool():
    validator = PolicyPatchValidator()
    invalid_tool_patch = PolicyPatch(
        patch_id="BAD-TOOL-001",
        target_policy="triage_screening",
        trigger="Acute symptoms",
        rule="Screen for symptoms and call unknown tool.",
        required_actions=["unknown_arbitrary_tool_call"],
        forbidden_actions=[],
        rationale="Invalid tool specified.",
        source_failure_id="FAIL-TEST",
        severity="HIGH"
    )
    is_valid, error = validator.validate(invalid_tool_patch)
    assert is_valid is False
    assert "not a recognized EHR tool" in error
