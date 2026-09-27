import unittest

import numpy as np

from SigProfilerExtractor.subroutines import integer_activities


class ActivityExportTest(unittest.TestCase):
    def test_activities_are_rounded_not_truncated(self):
        exposures = np.array([[0.4, 0.6, 0.99], [10.49, 10.51, 3.0]])
        np.testing.assert_array_equal(
            integer_activities(exposures), [[0, 1, 1], [10, 11, 3]]
        )
        self.assertTrue(np.issubdtype(integer_activities(exposures).dtype, np.integer))


if __name__ == "__main__":
    unittest.main()
