import ast
import inspect
import unittest

from SigProfilerExtractor import sigpro


class ContextLabelTest(unittest.TestCase):
    def test_no_chained_or_comparison_with_string_constants(self):
        # `x == "96" or "288"` is always true; guard against that pattern
        tree = ast.parse(inspect.getsource(sigpro))
        for node in ast.walk(tree):
            if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                for value in node.values[1:]:
                    self.assertFalse(
                        isinstance(value, ast.Constant) and isinstance(value.value, str),
                        "string constant used as an `or` operand at line {}".format(node.lineno),
                    )


if __name__ == "__main__":
    unittest.main()
