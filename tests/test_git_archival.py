import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class GitArchivalTest(unittest.TestCase):
    """A zip or tarball from GitHub has no git history. GitHub fills in
    .git_archival.txt when it builds one, and setuptools_scm reads the version
    from it; without it the version is "0+unknown"."""

    def test_github_fills_in_the_archival_file(self):
        attributes = (ROOT / ".gitattributes").read_text().split("\n")
        self.assertIn(".git_archival.txt  export-subst", attributes)

    def test_the_archival_file_names_the_commit_and_nearest_tag(self):
        text = (ROOT / ".git_archival.txt").read_text()
        self.assertIn("node: $Format:%H$", text)
        self.assertIn("describe-name: $Format:%(describe:tags=true,match=v[0-9]*)$", text)


if __name__ == "__main__":
    unittest.main()
