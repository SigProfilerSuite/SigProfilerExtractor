import unittest

import numpy as np
import pandas as pd

from SigProfilerExtractor.sigpro import check_input_samples


def matrix(**samples):
    data = pd.DataFrame({"MutationType": ["A[C>A]A", "A[C>G]A", "A[C>T]A"]})
    for name, values in samples.items():
        data[name] = values
    return data


class InputSamplesTest(unittest.TestCase):
    def test_clean_matrix_is_unchanged(self):
        data = matrix(s1=[1, 2, 3], s2=[4, 5, 6])
        cleaned, empty, zero = check_input_samples(data)
        pd.testing.assert_frame_equal(cleaned, data)
        self.assertEqual((empty, zero), ([], []))

    def test_empty_and_zero_columns_are_removed_and_reported(self):
        data = matrix(s1=[1, 2, 3], blank=[np.nan] * 3, s0=[0, 0, 0])
        cleaned, empty, zero = check_input_samples(data)
        self.assertEqual(list(cleaned.columns), ["MutationType", "s1"])
        self.assertEqual(empty, ["blank"])
        self.assertEqual(zero, ["s0"])

    def test_partly_missing_sample_is_an_error(self):
        data = matrix(s1=[1, 2, 3], s2=[4, np.nan, 6])
        with self.assertRaisesRegex(ValueError, r"s2 \(A\[C>G\]A\)"):
            check_input_samples(data)


if __name__ == "__main__":
    unittest.main()
