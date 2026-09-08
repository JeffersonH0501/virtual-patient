import unittest

from pydantic import ValidationError

from app.agents.schemas.evaluation import EvaluationResult
from app.controllers.interview_evaluation_controller import InterviewEvaluationController


class EvaluationScaleTests(unittest.TestCase):
    def test_score_accepts_zero_to_five_with_decimals(self) -> None:
        for score in (0, 2.9, 3, 3.9, 4, 5):
            result = EvaluationResult(aspect="test", score=score, feedback="Test feedback")
            self.assertEqual(result.score, score)

    def test_score_rejects_values_outside_zero_to_five(self) -> None:
        for score in (-0.1, 5.1):
            with self.assertRaises(ValidationError):
                EvaluationResult(aspect="test", score=score, feedback="Test feedback")

    def test_overall_score_preserves_one_decimal_place(self) -> None:
        controller = InterviewEvaluationController(db=None)
        results = [
            EvaluationResult(aspect="first", score=2.9, feedback="First"),
            EvaluationResult(aspect="second", score=4, feedback="Second"),
        ]

        self.assertEqual(controller.calculate_overall_score(results), 3.5)


if __name__ == "__main__":
    unittest.main()
