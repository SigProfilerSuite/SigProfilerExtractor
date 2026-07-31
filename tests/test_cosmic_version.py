import inspect
import unittest
from importlib import metadata, resources

import pandas as pd
from packaging.version import Version
from SigProfilerAssignment import decompose_subroutines

from SigProfilerExtractor import sigpro
from SigProfilerExtractor.controllers.cli_controller import parse_arguments_extractor


class CosmicVersionDefaultsTest(unittest.TestCase):
    def test_extractor_api_defaults_to_cosmic_v3_6(self):
        parameters = inspect.signature(sigpro.sigProfilerExtractor).parameters

        self.assertEqual(parameters["cosmic_version"].default, 3.6)
        self.assertEqual(sigpro.DEFAULT_COSMIC_VERSION, 3.6)
        self.assertIn(3.6, sigpro.SUPPORTED_COSMIC_VERSIONS)

    def test_cli_defaults_to_cosmic_v3_6(self):
        parsed_args = parse_arguments_extractor(
            ["matrix", "test-output", "test-input.tsv"],
            "Test parser",
        )

        self.assertEqual(parsed_args.cosmic_version, 3.6)

    def test_cli_preserves_explicit_older_cosmic_version(self):
        parsed_args = parse_arguments_extractor(
            [
                "matrix",
                "test-output",
                "test-input.tsv",
                "--cosmic_version",
                "3.5",
            ],
            "Test parser",
        )

        self.assertEqual(parsed_args.cosmic_version, 3.5)


class SigProfilerAssignmentCompatibilityTest(unittest.TestCase):
    def test_installed_assignment_version_supports_cosmic_v3_6(self):
        self.assertGreaterEqual(
            Version(metadata.version("SigProfilerAssignment")),
            Version("1.1.5"),
        )

    def test_assignment_packages_cosmic_v3_6_reference_matrices(self):
        reference_root = (
            resources.files("SigProfilerAssignment")
            / "data"
            / "Reference_Signatures"
        )
        expected_files = (
            ("GRCh37", "COSMIC_v3.6_SBS_GRCh37.txt"),
            ("GRCh37", "COSMIC_v3.6_SBS_GRCh37_exome.txt"),
            ("GRCh37", "COSMIC_v3.6_DBS_GRCh37.txt"),
            ("GRCh37", "COSMIC_v3.6_ID_GRCh37.txt"),
            ("GRCh37", "COSMIC_v3.6_CN_GRCh37.txt"),
            ("GRCh37", "COSMIC_v3.6_RNA-SBS_GRCh37.txt"),
            ("GRCh38", "COSMIC_v3.6_SBS_GRCh38.txt"),
            ("GRCh38", "COSMIC_v3.6_DBS_GRCh38.txt"),
            ("GRCh38", "COSMIC_v3.6_SV_GRCh38.txt"),
            ("mm9", "COSMIC_v3.6_SBS_mm9.txt"),
            ("mm10", "COSMIC_v3.6_SBS_mm10.txt"),
            ("mm39", "COSMIC_v3.6_SBS_mm39.txt"),
            ("rn6", "COSMIC_v3.6_SBS_rn6.txt"),
            ("rn7", "COSMIC_v3.6_SBS_rn7.txt"),
        )

        for genome, filename in expected_files:
            with self.subTest(genome=genome, filename=filename):
                reference_file = reference_root / genome / filename
                self.assertTrue(reference_file.is_file())
                self.assertGreater(len(reference_file.read_bytes()), 100)

    def test_assignment_loads_v3_6_references_for_supported_contexts(self):
        genomes = ("GRCh37", "GRCh38", "mm9", "mm10", "mm39", "rn6", "rn7")
        test_cases = [
            (rows, genome, exome)
            for rows in (96, 78)
            for genome in genomes
            for exome in (False, True)
        ]
        test_cases.extend(
            (
                (83, "GRCh37", False),
                (48, "GRCh37", False),
                (32, "GRCh38", False),
            )
        )

        for rows, genome, exome in test_cases:
            with self.subTest(rows=rows, genome=genome, exome=exome):
                samples = pd.DataFrame(index=range(rows))
                signatures, names, _, _ = decompose_subroutines.getProcessAvg(
                    samples,
                    genome_build=genome,
                    cosmic_version=sigpro.DEFAULT_COSMIC_VERSION,
                    exome=exome,
                )

                self.assertEqual(signatures.shape[0], rows)
                self.assertGreater(signatures.shape[1], 0)
                self.assertEqual(len(names), signatures.shape[1])


if __name__ == "__main__":
    unittest.main()
