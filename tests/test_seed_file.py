import os
import tempfile
import unittest

from SigProfilerExtractor.sigpro import read_seed_file


class SeedFileTest(unittest.TestCase):
    def write(self, text):
        handle, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(handle, "w") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_single_seed_is_read_as_int(self):
        seeds, seed = read_seed_file(self.write("\tSeed\n0\t2514338617901192340\n"))
        self.assertIsInstance(seed, int)
        self.assertEqual(seed, 2514338617901192340)
        self.assertEqual(len(seeds), 1)

    def test_multiple_seeds_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one seed"):
            read_seed_file(self.write("\tSeed\n0\t1\n1\t2\n"))

    def test_missing_seed_column_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must contain a 'Seed' column"):
            read_seed_file(self.write("\tValue\n0\t1\n"))


if __name__ == "__main__":
    unittest.main()
