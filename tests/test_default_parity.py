import inspect
import unittest

from SigProfilerExtractor import sigpro
from SigProfilerExtractor.controllers.cli_controller import parse_arguments_extractor


class DefaultParityTest(unittest.TestCase):
    def test_api_and_cli_share_maximum_signatures_default(self):
        api_default = (
            inspect.signature(sigpro.sigProfilerExtractor)
            .parameters["maximum_signatures"]
            .default
        )
        cli_args = parse_arguments_extractor(
            ["matrix", "test-output", "test-input.tsv"], "Test parser"
        )
        self.assertEqual(api_default, sigpro.DEFAULT_MAXIMUM_SIGNATURES)
        self.assertEqual(cli_args.maximum_signatures, api_default)

    def test_api_and_cli_enable_dashboard_by_default(self):
        api_default = (
            inspect.signature(sigpro.sigProfilerExtractor)
            .parameters["make_dashboard"]
            .default
        )
        cli_args = parse_arguments_extractor(
            ["matrix", "test-output", "test-input.tsv"], "Test parser"
        )
        self.assertTrue(api_default)
        self.assertEqual(cli_args.make_dashboard, api_default)

    def test_cli_can_disable_dashboard(self):
        cli_args = parse_arguments_extractor(
            [
                "matrix",
                "test-output",
                "test-input.tsv",
                "--make_dashboard",
                "false",
            ],
            "Test parser",
        )
        self.assertFalse(cli_args.make_dashboard)


if __name__ == "__main__":
    unittest.main()
