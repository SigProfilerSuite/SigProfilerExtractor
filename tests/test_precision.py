import unittest

import numpy as np
import torch

from SigProfilerExtractor.subroutines import genomes_tensor


class PrecisionTest(unittest.TestCase):
    def test_double_keeps_float64_values(self):
        genomes = np.array([[1.0 + 1e-12, 2.0]])
        tensor = genomes_tensor(genomes, "double")
        self.assertEqual(tensor.dtype, torch.float64)
        self.assertEqual(float(tensor[0, 0]), 1.0 + 1e-12)

    def test_single_is_float32(self):
        tensor = genomes_tensor(np.array([[1.0, 2.0]]), "single")
        self.assertEqual(tensor.dtype, torch.float32)


if __name__ == "__main__":
    unittest.main()
