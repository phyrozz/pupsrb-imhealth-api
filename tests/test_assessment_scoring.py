"""Pure offline checks for the assessment response and scenario rules."""
import ast
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "services" / "assessments" / "submit_assessment.py"
MODULE = ast.parse(SOURCE.read_text())
NAMESPACE = {}

for node in MODULE.body:
    if isinstance(node, ast.FunctionDef) and node.name in {
        "_normalise_responses", "_has_response_at_least", "_compute_apriori"
    }:
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), NAMESPACE)
    elif isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id in {"RESPONSE_VALUES", "DOMAIN_QUESTIONS"}
        for target in node.targets
    ):
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), NAMESPACE)


class AssessmentScoringTests(unittest.TestCase):
    def test_labels_are_stored_as_the_legacy_zero_to_four_scale(self):
        self.assertEqual(
            NAMESPACE["_normalise_responses"](["Not at all", "Slight", "Mild", "Moderate", "Severe"]),
            [0, 1, 2, 3, 4],
        )

    def test_invalid_response_is_rejected(self):
        with self.assertRaises(ValueError):
            NAMESPACE["_normalise_responses"](["Unknown rating"])

    def test_legacy_scenario_precedence(self):
        score = NAMESPACE["_compute_apriori"]
        self.assertEqual(score([0] * 23, None), 0)
        self.assertEqual(score([0] * 10 + [1] + [0] * 12, None), 2)
        self.assertEqual(score([0] * 5 + [3] + [0] * 17, None), 3)
        previous = [0] * 23
        previous[0] = 2
        self.assertEqual(score([0] * 23, previous), 1)

    def test_historical_labels_can_be_normalised_before_comparison(self):
        normalise = NAMESPACE["_normalise_responses"]
        score = NAMESPACE["_compute_apriori"]
        previous = normalise(["Mild"] + ["Not at all"] * 22)
        self.assertEqual(score([0] * 23, previous), 1)


if __name__ == "__main__":
    unittest.main()
