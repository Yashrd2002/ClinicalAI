from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from src.agent.policies import PolicyStore, PolicyPatch
from src.llm.client import LLMClient
from src.evals.runner import EvaluationRunner, BenchmarkSummary
from src.optimizer.failure_object import FailureReport
from src.optimizer.root_cause import RootCauseAnalyzer
from src.optimizer.patch_validator import PolicyPatchValidator


class ClosedLoopResult(BaseModel):
    decision: str  # "ACCEPTED" or "REJECTED"
    decision_reason: str
    target_scenario_id: str
    candidate_patch: PolicyPatch
    baseline_summary: BenchmarkSummary
    shadow_summary: BenchmarkSummary
    score_delta: float
    pass_rate_delta: float
    critical_failures_delta: int
    regressions: List[str] = Field(default_factory=list)


class ClosedLoopOptimizer:
    """
    Orchestrates the evidence-driven self-improvement loop:
    Observe -> Evaluate -> Diagnose -> Propose -> Validate -> Regression Test -> Accept / Reject
    """
    def __init__(self, llm_client: Optional[LLMClient] = None, policy_store: Optional[PolicyStore] = None):
        self.llm_client = llm_client or LLMClient()
        self.policy_store = policy_store or PolicyStore()
        self.rca = RootCauseAnalyzer()
        self.validator = PolicyPatchValidator()

    def run_optimization_cycle(self) -> ClosedLoopResult:
        # Step 1: Baseline Evaluation
        baseline_runner = EvaluationRunner(llm_client=self.llm_client, policy_store=self.policy_store)
        baseline_summary = baseline_runner.run_benchmark()

        if not baseline_summary.failure_reports:
            # No failures to optimize
            dummy_patch = PolicyPatch(
                patch_id="NOOP",
                target_policy="none",
                trigger="none",
                rule="none",
                rationale="Benchmark already passing with 100% score.",
                source_failure_id="NONE",
                severity="NONE"
            )
            return ClosedLoopResult(
                decision="REJECTED",
                decision_reason="No failures detected in baseline evaluation. Agent is already operating at peak benchmark performance.",
                target_scenario_id="NONE",
                candidate_patch=dummy_patch,
                baseline_summary=baseline_summary,
                shadow_summary=baseline_summary,
                score_delta=0.0,
                pass_rate_delta=0.0,
                critical_failures_delta=0
            )

        # Step 2: Extract Primary Failure
        target_failure: FailureReport = baseline_summary.failure_reports[0]

        # Step 3: Diagnose & Propose Candidate PolicyPatch
        candidate_patch = self.rca.diagnose_and_propose(target_failure)

        # Step 4: Validate Candidate Patch Schema & Safety Invariants
        is_valid, validation_error = self.validator.validate(candidate_patch)
        if not is_valid:
            return ClosedLoopResult(
                decision="REJECTED",
                decision_reason=f"Patch rejected by safety validator: {validation_error}",
                target_scenario_id=target_failure.scenario_id,
                candidate_patch=candidate_patch,
                baseline_summary=baseline_summary,
                shadow_summary=baseline_summary,
                score_delta=0.0,
                pass_rate_delta=0.0,
                critical_failures_delta=0
            )

        # Step 5: Shadow Sandbox Evaluation (Apply to in-memory clone)
        shadow_policy_store = self.policy_store.clone()
        shadow_policy_store.apply_patch(candidate_patch)

        shadow_runner = EvaluationRunner(llm_client=self.llm_client, policy_store=shadow_policy_store)
        shadow_summary = shadow_runner.run_benchmark()

        # Step 6: Multi-Dimensional Regression & Acceptance Gating
        target_shadow_res = next((r for r in shadow_summary.results if r.scenario_id == target_failure.scenario_id), None)
        target_fixed = target_shadow_res.passed if target_shadow_res else False

        # Detect regressions on previously passing scenarios
        regressions = []
        for base_res in baseline_summary.results:
            if base_res.passed:
                shadow_res = next((r for r in shadow_summary.results if r.scenario_id == base_res.scenario_id), None)
                if not shadow_res or not shadow_res.passed or shadow_res.final_score < (base_res.final_score - 5.0):
                    regressions.append(base_res.scenario_id)

        no_critical_failures = (shadow_summary.critical_failures_count == 0)
        score_improved = (shadow_summary.overall_score >= baseline_summary.overall_score)

        score_delta = round(shadow_summary.overall_score - baseline_summary.overall_score, 1)
        pass_rate_delta = round(shadow_summary.pass_rate - baseline_summary.pass_rate, 1)
        crit_delta = shadow_summary.critical_failures_count - baseline_summary.critical_failures_count

        # Step 7: Accept / Reject Decision
        if target_fixed and not regressions and no_critical_failures and score_improved:
            # ACCEPT: Commit to active policy store
            self.policy_store.apply_patch(candidate_patch)
            self.policy_store.save_policies()
            decision = "ACCEPTED"
            decision_reason = (
                f"Patch successfully resolved target failure ({target_failure.scenario_id}), "
                f"eliminated all critical safety failures ({baseline_summary.critical_failures_count} -> 0), "
                f"improved overall benchmark score by +{score_delta}%, and caused ZERO regressions."
            )
        else:
            decision = "REJECTED"
            reasons = []
            if not target_fixed:
                reasons.append(f"Target scenario {target_failure.scenario_id} still failed")
            if regressions:
                reasons.append(f"Regressions detected on scenarios: {regressions}")
            if not no_critical_failures:
                reasons.append(f"Remaining critical safety failures: {shadow_summary.critical_failures_count}")
            if not score_improved:
                reasons.append("Overall benchmark score degraded")
            decision_reason = f"Patch rejected by regression gate: {'; '.join(reasons)}"

        return ClosedLoopResult(
            decision=decision,
            decision_reason=decision_reason,
            target_scenario_id=target_failure.scenario_id,
            candidate_patch=candidate_patch,
            baseline_summary=baseline_summary,
            shadow_summary=shadow_summary,
            score_delta=score_delta,
            pass_rate_delta=pass_rate_delta,
            critical_failures_delta=crit_delta,
            regressions=regressions
        )
