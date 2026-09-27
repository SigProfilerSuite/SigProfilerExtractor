import unittest

import numpy as np

from SigProfilerExtractor.subroutines import calculate_similarities, replicate_diagnostics


class ReplicateDiagnosticsTest(unittest.TestCase):
    def test_metrics_describe_the_fitted_matrix(self):
        rng = np.random.default_rng(0)
        W = rng.random((96, 3))
        H = rng.random((3, 20)) * 100
        genomes = W @ H + rng.random((96, 20))
        values = replicate_diagnostics(genomes, W, H, convergence=30000)

        expected = calculate_similarities(genomes, W @ H, sample_names=False)[0].iloc[:, 2:]
        self.assertEqual(len(values), expected.shape[1] + 1)
        np.testing.assert_allclose(values[:-1], expected.mean(axis=0).to_numpy())
        self.assertEqual(values[-1], 30000)

    def test_exact_fit_has_zero_error(self):
        rng = np.random.default_rng(1)
        W = rng.random((96, 2))
        H = rng.random((2, 10)) * 50
        values = replicate_diagnostics(W @ H, W, H, convergence=1)
        self.assertAlmostEqual(values[0], 0.0, places=6)  # L1 error


if __name__ == "__main__":
    unittest.main()
