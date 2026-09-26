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


if __name__ == "__main__":
    unittest.main()
