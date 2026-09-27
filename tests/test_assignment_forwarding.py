import ast
import inspect
import unittest

from SigProfilerAssignment import decomposition

from SigProfilerExtractor import sigpro

FORWARDED = (
    "nnls_add_penalty",
    "nnls_remove_penalty",
    "initial_remove_penalty",
    "collapse_to_SBS96",
)


class AssignmentForwardingTest(unittest.TestCase):
    def spa_analyze_keywords(self):
        tree = ast.parse(inspect.getsource(sigpro))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "spa_analyze"
        ]
        self.assertEqual(len(calls), 1)
        return {kw.arg: kw.value for kw in calls[0].keywords}

    def test_fitting_parameters_are_forwarded(self):
        keywords = self.spa_analyze_keywords()
        for name in FORWARDED:
            self.assertIn(name, keywords)
            self.assertIsInstance(keywords[name], ast.Name)
            self.assertEqual(keywords[name].id, name)

    def test_assignment_accepts_forwarded_parameters(self):
        accepted = inspect.signature(decomposition.spa_analyze).parameters
        for name in FORWARDED:
            self.assertIn(name, accepted)


if __name__ == "__main__":
    unittest.main()
