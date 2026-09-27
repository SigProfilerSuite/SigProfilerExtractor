import unittest

import numpy as np

from SigProfilerExtractor.subroutines import get_normalization_cutoff


def cohort():
    # sample totals from two overlapping groups, so the GMM fit is not trivial
    rng = np.random.default_rng(0)
    totals = np.concatenate([rng.normal(3000, 900, 60), rng.normal(9000, 2500, 25)])
    totals = np.clip(totals, 200, None)
    return np.tile(totals / 96.0, (96, 1))


class NormalizationCutoffTest(unittest.TestCase):
    def test_same_random_state_gives_same_cutoff(self):
        data = cohort()
        cutoffs = set()
        for global_seed in range(5):
            np.random.seed(global_seed)  # the global state must not matter
            cutoffs.add(int(get_normalization_cutoff(data, manual_cutoff=0, random_state=7)))
        self.assertEqual(len(cutoffs), 1)


if __name__ == "__main__":
    unittest.main()
