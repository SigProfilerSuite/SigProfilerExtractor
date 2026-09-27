import unittest

import numpy as np
import pandas as pd

from SigProfilerExtractor.subroutines import silhouette_stability


def replicate_signatures(n_signatures, n_replicates, noise=0.01):
    rng = np.random.default_rng(0)
    centres = rng.random((n_signatures, 96))
    rows, labels = [], []
    for k in range(n_signatures):
        for _ in range(n_replicates):
            rows.append(centres[k] + noise * rng.random(96))
            labels.append(k)
    return pd.DataFrame(rows), labels


class SilhouetteStabilityTest(unittest.TestCase):
    def test_well_separated_clusters(self):
        clusters, labels = replicate_signatures(3, 10)
        values = silhouette_stability(clusters, labels, "cosine")
        self.assertEqual(len(values), 30)
        self.assertGreater(values.mean(), 0.8)

    def test_rank_one_is_stable_by_convention(self):
        clusters, labels = replicate_signatures(1, 10)
        np.testing.assert_array_equal(silhouette_stability(clusters, labels, "cosine"), 1.0)

    def test_single_replicate_is_rejected(self):
        clusters, labels = replicate_signatures(3, 1)
        with self.assertRaises(ValueError):
            silhouette_stability(clusters, labels, "cosine")

    def test_other_failures_are_not_reported_as_stable(self):
        clusters, labels = replicate_signatures(3, 10)
        clusters.iloc[0, 0] = np.nan
        with self.assertRaises(RuntimeError):
            silhouette_stability(clusters, labels, "cosine")


if __name__ == "__main__":
    unittest.main()
