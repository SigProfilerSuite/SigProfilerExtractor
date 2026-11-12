import ntpath
import os
import pathlib
import posixpath
import unittest

import pandas as pd

from SigProfilerExtractor.sigpro import input_project_name


class InputProjectNameTest(unittest.TestCase):
    def test_a_windows_path_gives_the_folder_name(self):
        # Splitting on "/" kept the whole path, and SigProfilerMatrixGenerator's
        # log file name then held a ":" (OSError: Invalid argument on Windows).
        for given in (
            r"C:\Users\me\AppData\Local\SigProfilerExtractor\jobs\746ee7bd7fa4\input",
            "C:\\Users\\me\\vcfs\\",
            "C:/Users/me/vcfs",
            r"\\server\share\vcfs",
        ):
            with self.subTest(given=given):
                self.assertNotIn(":", input_project_name(given, path=ntpath))
        self.assertEqual(input_project_name(r"C:\data\jobs\x\input", path=ntpath), "input")
        self.assertEqual(input_project_name("C:\\data\\vcfs\\", path=ntpath), "vcfs")
        self.assertEqual(input_project_name("C:/data/vcfs", path=ntpath), "vcfs")

    def test_posix_paths_keep_their_old_names(self):
        self.assertEqual(input_project_name("/data/vcfs", path=posixpath), "vcfs")
        self.assertEqual(input_project_name("/data/vcfs/", path=posixpath), "vcfs")
        self.assertEqual(input_project_name("data/Samples_SBS.txt", path=posixpath), "Samples_SBS.txt")

    def test_this_platforms_paths(self):
        folder = os.path.join("data", "vcfs")
        self.assertEqual(input_project_name(folder), "vcfs")
        self.assertEqual(input_project_name(folder + os.sep), "vcfs")
        self.assertEqual(input_project_name(pathlib.Path(folder)), "vcfs")

    def test_input_that_is_not_a_path(self):
        self.assertEqual(input_project_name(pd.DataFrame({"a": [1]})), "Input from DataFrame")
        self.assertEqual(input_project_name(""), "Input from DataFrame")
        self.assertEqual(input_project_name(None), "Input from DataFrame")


if __name__ == "__main__":
    unittest.main()
