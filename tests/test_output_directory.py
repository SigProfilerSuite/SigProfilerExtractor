import os
import tempfile
import unittest

from SigProfilerExtractor.sigpro import move_previous_results


class OutputDirectoryTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.context = os.path.join(self.root.name, "SBS96")

    def test_missing_or_empty_directory_is_left_alone(self):
        self.assertIsNone(move_previous_results(self.context))
        os.makedirs(self.context)
        self.assertIsNone(move_previous_results(self.context))
        self.assertTrue(os.path.isdir(self.context))

    def test_previous_results_are_moved_not_deleted(self):
        stale = os.path.join(self.context, "All_Solutions", "SBS96_10_Signatures")
        os.makedirs(stale)
        first = move_previous_results(self.context)
        self.assertFalse(os.path.exists(self.context))
        self.assertTrue(os.path.isdir(os.path.join(first, "All_Solutions", "SBS96_10_Signatures")))

        os.makedirs(stale)
        second = move_previous_results(self.context)
        self.assertNotEqual(first, second)
        self.assertTrue(os.path.isdir(first) and os.path.isdir(second))


if __name__ == "__main__":
    unittest.main()
