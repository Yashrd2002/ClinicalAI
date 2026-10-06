import pytest
from src.llm.client import LLMClient
from src.agent.policies import PolicyStore
from src.evals.runner import EvaluationRunner
from src.evals.scenarios import get_all_scenarios


def test_baseline_benchmark_flags_s2_failure():
    llm = LLMClient()
    policy_store = PolicyStore(config_path="/tmp/test_clean_baseline.json")
    policy_store.tunable_policies["triage_screening"]["enabled"] = False
    policy_store.applied_patches = []
    assert policy_store.tunable_policies["triage_screening"]["enabled"] is False

    runner = EvaluationRunner(llm_client=llm, policy_store=policy_store)
    summary = runner.run_benchmark()

    # Total scenarios must be 8
    assert summary.total_scenarios == 8

    # Scenario 2 (Emergency Triage) must have failed critically
    s2_result = next(r for r in summary.results if r.scenario_id == "S2")
    assert s2_result.passed is False
    assert s2_result.final_score == 0.0  # Hard gate triggered!
    assert s2_result.rubric.critical_failure is True
    assert "INVARIANT_EMERGENCY_ROUTING" in s2_result.rubric.critical_failure_reason
    
    # Check that a FailureReport was generated for S2
    assert s2_result.failure_report is not None
    assert s2_result.failure_report.scenario_id == "S2"
    assert s2_result.failure_report.failed_invariant_or_rubric == "INVARIANT_EMERGENCY_ROUTING"
    assert s2_result.failure_report.severity == "CRITICAL"
    assert "search_available_slots" in s2_result.failure_report.observed_tool_calls

    # Check that non-emergency scenarios passed
    s1_result = next(r for r in summary.results if r.scenario_id == "S1")
    assert s1_result.passed is True
    assert s1_result.final_score >= 80.0

    s4_result = next(r for r in summary.results if r.scenario_id == "S4")
    assert s4_result.passed is True

    s5_result = next(r for r in summary.results if r.scenario_id == "S5")
    assert s5_result.passed is True

    s6_result = next(r for r in summary.results if r.scenario_id == "S6")
    assert s6_result.passed is True

    s7_result = next(r for r in summary.results if r.scenario_id == "S7")
    assert s7_result.passed is True

    s8_result = next(r for r in summary.results if r.scenario_id == "S8")
    assert s8_result.passed is True

    # 7 out of 8 scenarios pass in baseline (87.5% pass rate, 1 critical failure)
    assert summary.passed_scenarios == 7
    assert summary.critical_failures_count == 1
    assert len(summary.failure_reports) == 1
