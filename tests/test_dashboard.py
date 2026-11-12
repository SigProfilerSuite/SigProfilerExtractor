import json
import re
import tempfile
import unittest
from pathlib import Path

from SigProfilerExtractor.dashboard import DashboardError, _safe_json, create_dashboard


SBS6 = ("C>A", "C>G", "C>T", "T>A", "T>C", "T>G")
ROOT_SEED = "278390142581741370537812005101985235401"


def write_table(path, header, rows, delimiter="\t"):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [delimiter.join(map(str, header))]
    lines.extend(delimiter.join(map(str, row)) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.output = Path(self.temporary.name) / "example-results"
        context = self.output / "SBS6"
        solution = context / "All_Solutions" / "SBS6_2_Signatures"

        write_table(
            context / "All_solutions_stat.csv",
            [
                "Signatures",
                "Stability (Avg Silhouette)",
                "Minimum Stability",
                "Considerable Solution",
                "Matrix Frobenius%",
                "Mean Cosine Distance",
            ],
            [["2*", 0.91, 0.82, "YES", "4.5%", 0.012]],
            delimiter=",",
        )
        write_table(
            context / "Samples.txt",
            ["MutationType", "Sample-1", "Sample-2"],
            [(label, index + 2, index + 4) for index, label in enumerate(SBS6)],
        )
        write_table(
            solution / "Signatures" / "SBS6_S2_Signatures.txt",
            ["MutationType", "SBS6A", "SBS6B"],
            [(label, (index + 1) / 21, (6 - index) / 21) for index, label in enumerate(SBS6)],
        )
        write_table(
            solution / "Activities" / "SBS6_S2_NMF_Activities.txt",
            ["Samples", "SBS6A", "SBS6B"],
            [["Sample-1", 20, 10], ["Sample-2", 5, 30]],
        )
        write_table(
            solution / "Solution_Stats" / "SBS6_S2_Signatures_stats.txt",
            ["Signatures", "Stability", "Total Mutations"],
            [["SBS6A", 0.95, 25], ["SBS6B", 0.87, 40]],
        )
        write_table(
            solution / "Solution_Stats" / "SBS6_S2_Samples_stats.txt",
            ["Sample Names", "Total Mutations", "Cosine Similarity", "L1_Norm_%"],
            [["Sample-1", 30, 0.98, "6.1%"], ["Sample-2", 35, 0.97, "7.2%"]],
        )
        write_table(
            solution / "Solution_Stats" / "SBS6_S2_NMF_Convergence_Information.txt",
            ["NMF_Replicate", "KL Divergence", "Correlation", "Convergence Iterations"],
            [[1, 0.02, 0.98, 100], [2, 0.018, 0.99, 120]],
        )
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "JOB_METADATA.txt").write_text("completed\n", encoding="utf-8")
        write_table(self.output / "Seeds.txt", ["Index", "Seed"], [[0, ROOT_SEED]])

    def tearDown(self):
        self.temporary.cleanup()

    def test_builds_self_contained_dashboard_with_rank_figures(self):
        dashboard = create_dashboard(self.output)

        self.assertEqual(dashboard.name, "reports.html")
        html = dashboard.read_text(encoding="utf-8")
        self.assertIn("SigProfilerExtractor", html)
        self.assertIn("All solutions", html)
        self.assertIn('id="figureHelpDialog"', html)
        self.assertIn("Explain this figure", html)
        self.assertIn("Mutational signature profile", html)
        self.assertIn("Burden: high to low", html)
        self.assertIn("Matrix Frobenius error (%)", html)
        self.assertIn("aria-sort", html)
        self.assertIn("window.location.hash", html)
        self.assertNotRegex(html, r'<(?:script|link)[^>]+(?:src|href)="https?://')

        match = re.search(
            r'<script id="dashboardData" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))
        context = payload["contexts"][0]
        self.assertEqual(context["name"], "SBS6")
        self.assertEqual(context["selected_rank"], 2)
        self.assertEqual(context["sample_summary"]["samples"], 2)
        self.assertEqual(payload["seeds"]["rows"][0][1], ROOT_SEED)
        self.assertEqual(context["solutions"][0]["signatures"]["names"], ["SBS6A", "SBS6B"])
        self.assertEqual(
            context["solutions"][0]["signatures"]["figures"]["SBS6A"]["kind"],
            "standard",
        )

    def test_side_panel_can_be_resized_and_hidden(self):
        html = create_dashboard(self.output).read_text(encoding="utf-8")
        self.assertIn('id="sidebarToggle"', html)
        self.assertIn('aria-controls="dashboardSidebar"', html)
        self.assertRegex(html, r'id="sidebarSplitter" role="separator" aria-orientation="vertical"')
        # The view tabs are found as ".tabs button": the panel button must not be one.
        tabs = re.search(r'<nav class="tabs".*?</nav>', html, re.DOTALL).group(0)
        self.assertNotIn("sidebarToggle", tabs)

    def test_rejects_directory_without_completed_context(self):
        empty = Path(self.temporary.name) / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(DashboardError, "No completed mutation-context"):
            create_dashboard(empty)

    def test_json_cannot_close_its_script_element(self):
        encoded = _safe_json({"name": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script>", encoded)
        self.assertIn("\\u003c", encoded)

    def test_requires_browser_openable_html_filename(self):
        with self.assertRaisesRegex(DashboardError, "plain .html filename"):
            create_dashboard(self.output, "reports.dashboard")


if __name__ == "__main__":
    unittest.main()
