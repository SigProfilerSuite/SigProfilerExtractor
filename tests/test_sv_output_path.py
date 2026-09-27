import os
import unittest

from SigProfilerExtractor.sigpro import sv_matrix_directory


class SVOutputPathTest(unittest.TestCase):
    def test_trailing_slash_does_not_change_the_output_folder(self):
        expected = os.path.join("/data", "SV_Matrices")
        self.assertEqual(sv_matrix_directory("/data/sv"), expected)
        self.assertEqual(sv_matrix_directory("/data/sv/"), expected)
        self.assertEqual(sv_matrix_directory("/data/sv//"), expected)


if __name__ == "__main__":
    unittest.main()
