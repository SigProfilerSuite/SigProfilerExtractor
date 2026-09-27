import unittest

import numpy as np
import pandas as pd

from SigProfilerExtractor.subroutines import check_matrix_normalization, normalize_samples


class MatrixNormalizationTest(unittest.TestCase):
    def test_named_methods_and_numeric_cutoffs_are_accepted(self):
        for norm in ("gmm", "100X", "log2", "none", 5000, "5000"):
            check_matrix_normalization(norm)

    def test_unknown_values_are_rejected(self):
        for norm in ("custom", "no_normalization", "Log2", 0, -5, "5000.5", None):
            with self.assertRaises(ValueError, msg=repr(norm)):
                check_matrix_normalization(norm)

    def test_numeric_cutoff_scales_samples_above_it(self):
        genomes = pd.DataFrame(np.array([[10.0, 300.0], [10.0, 700.0]]))
        totals = genomes.sum(axis=0)
        result = np.array(normalize_samples(genomes, totals, norm="100"))
        np.testing.assert_allclose(result[:, 0], [10.0, 10.0])  # 20 <= 100: unchanged
        np.testing.assert_allclose(result[:, 1], [30.0, 70.0])  # 1000 -> 100
        with self.assertRaises(ValueError):
            normalize_samples(genomes, totals, norm="custom")


if __name__ == "__main__":
    unittest.main()
