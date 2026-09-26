import ast
import pathlib
import subprocess
import sys
import textwrap
import unittest

import SigProfilerExtractor

PACKAGE = pathlib.Path(SigProfilerExtractor.__file__).parent
GLOBAL_CALLS = {"filterwarnings", "simplefilter", "set_start_method"}

CHECK = textwrap.dedent(
    """
    import multiprocessing
    import SigProfilerExtractor.subroutines as sub
    from SigProfilerExtractor import sigpro

    assert multiprocessing.get_start_method(allow_none=True) is None, "start method was set"
    assert sub.SPAWN.get_start_method() == "spawn"
    """
)


class ImportSideEffectsTest(unittest.TestCase):
    def test_import_does_not_set_the_start_method(self):
        # run in a fresh interpreter, because other tests may already have imported the package
        result = subprocess.run(
            [sys.executable, "-c", CHECK], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_module_level_global_settings(self):
        # warning filters or a start method set at import time would change the host program
        for path in PACKAGE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    func = node.value.func
                    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                    self.assertNotIn(name, GLOBAL_CALLS, "{}:{}".format(path.name, node.lineno))


if __name__ == "__main__":
    unittest.main()
