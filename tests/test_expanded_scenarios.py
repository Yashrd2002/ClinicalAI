import pytest
from src.evals.expanded_scenarios import load_expanded_scenarios


def test_expanded_scenarios_schema_and_integrity():
    scenarios = load_expanded_scenarios()
    assert len(scenarios) == 50, f"Expected 50 scenarios, found {len(scenarios)}"

    seen_ids = set()
    for s in scenarios:
        # 1. Unique ID
        assert s.id not in seen_ids, f"Duplicate scenario ID: {s.id}"
        seen_ids.add(s.id)

        # 2. Non-empty name and presentation
        assert s.name.strip(), f"Scenario {s.id} has empty name"
        assert s.clinical_presentation.strip(), f"Scenario {s.id} has empty presentation"

        # 3. Steps integrity
        assert len(s.steps) >= 1, f"Scenario {s.id} has no dialogue steps"
        for st in s.steps:
            assert st.strip(), f"Scenario {s.id} has empty step utterance"

        # 4. Invariants integrity
        assert len(s.invariants_to_enforce) >= 1, f"Scenario {s.id} has no expected invariants"

        # 5. Converted ScenarioDefinition parity
        def_obj = s.to_scenario_definition()
        assert def_obj.id == s.id
        assert len(def_obj.steps) == len(s.steps)
