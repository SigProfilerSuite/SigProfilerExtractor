"""The Workbench in a real browser (Chromium via Playwright); skipped without it."""

import json
import threading
import time
from pathlib import Path

import pytest

playwright_sync_api = pytest.importorskip("playwright.sync_api")

from SigProfilerExtractor.web import jobs, server  # noqa: E402

DATA = Path(server.__file__).resolve().parents[1] / "data"
SBS = str(DATA / "TextInput" / "Samples_SBS.txt")


@pytest.fixture
def dashboard_url(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "RUNJOB_MODULE", "tests.web.fixtures.fake_runjob")
    monkeypatch.setattr(server.genomes, "installed_genomes", lambda volume=None: ["GRCh37"])
    srv = server.make_server("127.0.0.1", 0, tmp_path / "jobs")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/"
    finally:
        srv.shutdown()
        thread.join(timeout=5)
        srv.server_close()


@pytest.fixture
def page(dashboard_url):
    with playwright_sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        browser_page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        browser_page.on("pageerror", lambda e: errors.append(str(e)))
        browser_page.goto(dashboard_url)
        browser_page.wait_for_selector("#exampleSel option[value='sbs96']", state="attached")
        yield browser_page
        browser.close()
        assert errors == [], f"uncaught page errors: {errors}"


def _wait_text(locator, needle, timeout=10.0):
    deadline = time.monotonic() + timeout
    text = ""
    while time.monotonic() < deadline:
        text = locator.text_content() or ""
        if needle in text:
            return text
        time.sleep(0.05)
    raise AssertionError(f"{needle!r} never appeared (last text: {text[:300]!r})")


def _wait_until(check, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("condition never became true")


def _matrix_input(page, path=SBS):
    page.check("input[name='kind'][value='matrix']")
    page.fill("#inputPath", path)
    page.press("#inputPath", "Enter")
    page.wait_for_selector("#inputInfo .tile")


def _spe_output(root, dashboard=True):
    ctx = root / "SBS96"
    (ctx / "All_Solutions" / "SBS96_2_Signatures" / "Signatures").mkdir(parents=True)
    (ctx / "All_solutions_stat.csv").write_text("Signatures,x\n1,0.9\n2*,0.8\n")
    (ctx / "Samples.txt").write_text("MutationType\tS1\tS2\n")
    (ctx / "SBS96_selection_plot.pdf").write_bytes(b"%PDF-1.4\n")
    sig = ctx / "Suggested_Solution" / "SBS96_De-Novo_Solution" / "Signatures"
    sig.mkdir(parents=True)
    (sig / "SBS96_De-Novo_Signatures.txt").write_text("MutationType\tSBS96A\tSBS96B\n")
    (root / "JOB_METADATA.txt").write_text("-------Job Status-------\nAnalysis of mutational signatures completed successfully!\n")
    if dashboard:
        (root / "reports.html").write_text("<!doctype html><title>r</title><h1 id='hello'>Dashboard here</h1>")
    return root


# ------------------------------------------------------------------ home

def test_home_introduces_the_tool_and_its_buttons_lead_on(page):
    assert page.is_visible("#view-home")
    text = page.text_content("#view-home")
    for words in ("Find the mutational signatures", "You give", "You get", "How it works", "Benchmarked"):
        assert words in text
    assert page.locator(".how li").count() == 5
    page.click("#homeStart")
    assert page.is_visible("#view-run")
    page.click("#homeBtn")
    assert page.is_visible("#view-home")


def test_the_example_button_fills_in_a_ready_run(page):
    page.click("#homeExample")
    page.wait_for_selector("#inputInfo .tile")
    assert page.is_checked("input[name='kind'][value='matrix']")
    assert page.locator("#inputInfo .tile .v").all_text_contents()[:2] == ["SBS96", "21"]
    assert page.input_value("#outputPath").endswith("SigProfilerExtractor_example/Breast_SBS96")
    _wait_until(lambda: not page.is_disabled("#startBtn"))
    _wait_text(page.locator("#launchSummary"), "50 fits")


# --------------------------------------------------------------- new run

def test_the_form_follows_the_kind_of_input(page):
    page.click("#tab-run")
    assert page.text_content("#inputChooseText") == "Choose the folder of variant calls"
    assert page.is_visible("#contextChips") and not page.is_visible("#opportunitySel")
    page.check("input[name='kind'][value='seg']")
    assert page.text_content("#inputChooseText") == "Choose the segmentation file"
    assert page.is_visible("#segCaller") and page.is_visible("#opportunitySel")
    assert page.text_content("#genomeTitle") == "COSMIC reference"


def test_start_waits_for_what_is_missing_and_says_so(page):
    page.click("#tab-run")
    assert page.is_disabled("#startBtn")
    _wait_text(page.locator("#launchSummary"), "Choose the input.")
    _matrix_input(page)
    _wait_until(lambda: not page.is_disabled("#startBtn"))


def test_presets_estimate_and_custom(page, tmp_path):
    page.click("#tab-run")
    _matrix_input(page)
    assert (page.input_value("#minSig"), page.input_value("#maxSig"), page.input_value("#replicates")) == ("1", "5", "10")
    _wait_text(page.locator("#estimate"), "50")
    page.check("input[name='preset'][value='standard']")
    assert page.input_value("#maxSig") == "25"
    # 25 is capped at the 21 samples.
    _wait_text(page.locator("#estimate"), "Capped at 21")
    page.fill("#replicates", "7")
    page.dispatch_event("#replicates", "input")
    assert page.is_checked("input[name='preset'][value='custom']")
    page.fill("#minSig", "9")
    page.fill("#maxSig", "3")
    page.dispatch_event("#maxSig", "input")
    _wait_text(page.locator("#estimate"), "cannot be more than")
    assert page.is_disabled("#startBtn")


def test_a_matrix_with_empty_samples_says_which_will_be_dropped(page, tmp_path):
    m = tmp_path / "m.txt"
    rows = ["MutationType\tA\tB"] + [f"T{i}\t{i + 1}\t0" for i in range(96)]
    m.write_text("\n".join(rows) + "\n")
    page.click("#tab-run")
    _matrix_input(page, str(m))
    _wait_text(page.locator("#inputInfo"), "will be dropped")


def test_the_cosmic_genome_follows_the_matrix_context(page):
    page.click("#tab-run")
    _matrix_input(page, str(DATA / "TextInput" / "Samples_SV.txt"))
    _wait_until(lambda: page.input_value("#opportunitySel") == "GRCh38")


def test_advanced_settings_count_changes_and_restore(page):
    page.click("#tab-run")
    page.click("#advCard > summary")
    assert page.text_content("#advChanged") == "all default"
    page.fill("#stability", "0.7")
    page.dispatch_event("#stability", "input")
    _wait_text(page.locator("#advChanged"), "1 changed")
    page.click("#resetAdvanced")
    _wait_text(page.locator("#advChanged"), "all default")
    assert page.input_value("#stability") == "0.8"
    assert page.is_disabled("#gpu") or page.is_enabled("#gpu")


def test_an_output_folder_with_results_needs_a_choice(page, tmp_path):
    out = _spe_output(tmp_path / "out")
    page.click("#tab-run")
    _matrix_input(page)
    page.fill("#outputPath", str(out))
    page.dispatch_event("#outputPath", "input")
    _wait_text(page.locator("#outCheck"), "already holds results from an earlier run")
    assert page.is_disabled("#startBtn")
    page.click("#outCheck button[data-choice='new']")
    assert page.input_value("#outputPath") == str(tmp_path / "out_2")
    page.fill("#outputPath", str(out))
    page.dispatch_event("#outputPath", "input")
    page.locator("#outCheck button[data-choice='replace']").click()
    _wait_text(page.locator("#outCheck"), "deleted when the run starts")
    _wait_until(lambda: not page.is_disabled("#startBtn"))


# --------------------------------------------------------------- monitor

def test_a_run_starts_reaches_done_and_offers_its_results(page, tmp_path):
    page.click("#tab-run")
    _matrix_input(page)
    page.fill("#outputPath", str(tmp_path / "run"))
    page.dispatch_event("#outputPath", "input")
    _wait_until(lambda: not page.is_disabled("#startBtn"))
    page.click("#startBtn")
    page.wait_for_selector("#view-monitor:not(.hidden)")
    _wait_text(page.locator("#jobPill"), "done")
    assert page.is_visible("#jobResult button:has-text('Open results')")
    _wait_text(page.locator("#jobResult"), "SBS96: 3 signatures suggested")
    assert page.locator("#ctxProgress .ctx-row").count() == 1
    configs = list((tmp_path / "jobs").glob("*/config.json"))
    kwargs = json.loads(configs[0].read_text())["kwargs"]
    assert (kwargs["input_type"], kwargs["maximum_signatures"], kwargs["nmf_replicates"]) == ("matrix", 5, 10)


def test_runs_can_be_removed_with_undo_and_deleted(page, tmp_path):
    page.click("#tab-run")
    _matrix_input(page)
    page.fill("#outputPath", str(tmp_path / "run"))
    page.dispatch_event("#outputPath", "input")
    _wait_until(lambda: not page.is_disabled("#startBtn"))
    page.click("#startBtn")
    _wait_text(page.locator("#jobPill"), "done")
    row = page.locator("#jobList .runrow").first
    row.hover()
    row.locator("button.rm.hide").click()
    _wait_until(lambda: page.locator("#jobList .runrow").count() == 0)
    page.click("#toastAction")
    page.locator("#jobList .runrow").first.wait_for()
    page.locator("#jobList .runrow .item").first.click()
    page.click("#deleteBtn")
    page.wait_for_selector("#deleteDialog[open]")
    assert "cannot be undone" in page.text_content("#deleteText")
    page.click("#deleteGo")
    _wait_until(lambda: page.locator("#jobList .runrow").count() == 0)


# --------------------------------------------------------------- results

def test_results_show_contexts_the_sandboxed_dashboard_and_plots(page, tmp_path):
    out = _spe_output(tmp_path / "out")
    page.fill("#openPath", str(out))
    page.press("#openPath", "Enter")
    page.wait_for_selector("#view-results:not(.hidden)")
    _wait_text(page.locator("#ctxCards"), "SBS96")
    assert page.text_content("#ctxCards .ctx-big .v") == "2"
    frame_el = page.locator("#dashFrame")
    assert frame_el.get_attribute("sandbox") == "allow-scripts allow-downloads allow-popups"
    frame = page.frame_locator("#dashFrame")
    assert frame.locator("#hello").text_content() == "Dashboard here"
    assert "/api/results/dashboard?" in page.get_attribute("#dashOpen", "href")
    assert page.locator("#plotGroups .files .f").count() == 1
    _wait_text(page.locator("#fileList"), "JOB_METADATA.txt")


def test_a_folder_without_a_dashboard_offers_to_build_one(page, tmp_path):
    out = _spe_output(tmp_path / "out", dashboard=False)
    page.fill("#openPath", str(out))
    page.press("#openPath", "Enter")
    _wait_text(page.locator("#dashMissing"), "has no reports.html")
    assert page.is_visible("#dashMissing button:has-text('Build the dashboard')")
    assert not page.is_visible("#dashFrame")


# ---------------------------------------------------------------- layout

def test_phone_width_has_no_horizontal_overflow(dashboard_url):
    with playwright_sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            phone.goto(dashboard_url)
            phone.wait_for_selector("#exampleSel option[value='sbs96']", state="attached")
            for tab in ("home", "run", "monitor", "results", "help"):
                phone.click(f"#tab-{tab}")
                width = phone.evaluate("document.documentElement.scrollWidth")
                assert width <= 390, f"{tab} view is {width}px wide at a 390px viewport"
            # The side panel sits below the work area: nothing to resize or hide.
            assert phone.is_hidden("#sideToggle") and phone.is_hidden("#sideSplitter")
        finally:
            browser.close()


@pytest.mark.parametrize("theme", ["sandiego", "ualbany", "sigprofilersuite", "night"])
def test_every_theme_applies(page, theme):
    page.select_option("#themeSel", theme)
    assert page.get_attribute("html", "data-theme") == theme


def test_delete_works_before_the_runs_first_status_arrives(page, tmp_path):
    # On a slow machine the Monitor's first status poll can arrive after the
    # user clicks Delete; the button must not depend on it.
    page.click("#tab-run")
    _matrix_input(page)
    page.fill("#outputPath", str(tmp_path / "run"))
    page.dispatch_event("#outputPath", "input")
    _wait_until(lambda: not page.is_disabled("#startBtn"))
    page.click("#startBtn")
    _wait_text(page.locator("#jobPill"), "done")
    # Removing it from the list and undoing that clears the Monitor's run, as
    # in the run-list test this came from.
    row = page.locator("#jobList .runrow").first
    row.hover()
    row.locator("button.rm.hide").click()
    _wait_until(lambda: page.locator("#jobList .runrow").count() == 0)
    page.click("#toastAction")
    page.locator("#jobList .runrow").first.wait_for()

    # Hold the run's status responses back (only GET /api/jobs/<id>, not its log
    # or delete preview) rather than sleeping in the handler, which would block
    # Playwright's event loop while the 1 s polls pile up.
    held = []

    def status_only(url):
        return "/api/jobs/" in url and url.rstrip("/").count("/") == 5 and "?" not in url

    page.route(status_only, lambda route: held.append(route))  # a plain function: Playwright tags it
    page.locator("#jobList .runrow .item").first.click()
    page.click("#deleteBtn")
    page.wait_for_selector("#deleteDialog[open]", timeout=2000)
    assert held, "the run's status was held back, so the click came first"
    # continue_() before unroute(): unroute releases held routes itself.
    for route in held:
        route.continue_()
    page.unroute(status_only)


# ---------------------------------------------------- resizable side panels

def _width(page, selector):
    box = page.locator(selector).bounding_box()
    return round(box["width"]) if box else 0


def test_the_side_panel_resizes_hides_and_is_remembered(page):
    assert _width(page, "#sidebar") == 280
    handle = page.locator("#sideSplitter").bounding_box()
    page.mouse.move(handle["x"] + handle["width"] / 2, 300)
    page.mouse.down()
    page.mouse.move(420, 320, steps=6)
    page.mouse.up()
    assert _width(page, "#sidebar") == 420

    page.focus("#sideSplitter")
    page.keyboard.press("ArrowLeft")
    assert _width(page, "#sidebar") == 400

    page.click("#sideToggle")
    assert page.is_hidden("#sidebar")
    assert page.get_attribute("#sideToggle", "aria-expanded") == "false"
    main_wide = _width(page, ".main")

    page.reload()
    page.wait_for_selector("#exampleSel option[value='sbs96']", state="attached")
    assert page.is_hidden("#sidebar"), "hidden is remembered"
    assert _width(page, ".main") == main_wide
    page.dblclick("#sideSplitter")
    assert _width(page, "#sidebar") == 400, "comes back at its last width"


def test_dragging_the_handle_far_left_hides_the_panel(page):
    handle = page.locator("#sideSplitter").bounding_box()
    page.mouse.move(handle["x"] + handle["width"] / 2, 300)
    page.mouse.down()
    page.mouse.move(40, 300, steps=6)
    page.mouse.up()
    assert page.is_hidden("#sidebar")


def _synthetic_output(root):
    """A small SBS6 output SigProfilerExtractor's dashboard can be built from."""
    sbs6 = ("C>A", "C>G", "C>T", "T>A", "T>C", "T>G")

    def table(path, header, rows, sep="\t"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(sep.join(map(str, r)) for r in [header, *rows]) + "\n")

    ctx = root / "SBS6"
    sol = ctx / "All_Solutions" / "SBS6_2_Signatures"
    table(ctx / "All_solutions_stat.csv", ["Signatures", "Stability (Avg Silhouette)", "Minimum Stability",
          "Considerable Solution", "Matrix Frobenius%", "Mean Cosine Distance"],
          [["2*", 0.91, 0.82, "YES", "4.5%", 0.012]], sep=",")
    table(ctx / "Samples.txt", ["MutationType", "S1", "S2"], [(m, i + 2, i + 4) for i, m in enumerate(sbs6)])
    table(sol / "Signatures" / "SBS6_S2_Signatures.txt", ["MutationType", "SBS6A", "SBS6B"],
          [(m, (i + 1) / 21, (6 - i) / 21) for i, m in enumerate(sbs6)])
    table(sol / "Activities" / "SBS6_S2_NMF_Activities.txt", ["Samples", "SBS6A", "SBS6B"], [["S1", 20, 10], ["S2", 5, 30]])
    table(sol / "Solution_Stats" / "SBS6_S2_Signatures_stats.txt", ["Signatures", "Stability", "Total Mutations"],
          [["SBS6A", 0.95, 25], ["SBS6B", 0.87, 40]])
    table(sol / "Solution_Stats" / "SBS6_S2_Samples_stats.txt", ["Sample Names", "Total Mutations",
          "Cosine Similarity", "L1_Norm_%"], [["S1", 30, 0.98, "6.1%"], ["S2", 35, 0.97, "7.2%"]])
    table(sol / "Solution_Stats" / "SBS6_S2_NMF_Convergence_Information.txt", ["NMF_Replicate", "KL Divergence",
          "Correlation", "Convergence Iterations"], [[1, 0.02, 0.98, 100], [2, 0.018, 0.99, 120]])
    (root / "JOB_METADATA.txt").write_text("completed\n")
    return root


def test_the_dashboards_own_panel_resizes_and_hides_inside_its_sandbox(page, tmp_path):
    from SigProfilerExtractor.dashboard import create_dashboard

    out = _synthetic_output(tmp_path / "out")
    create_dashboard(out)
    # Wide enough that the frame is above the dashboard's own 980 px narrow layout.
    page.set_viewport_size({"width": 1600, "height": 900})
    page.fill("#openPath", str(out))
    page.press("#openPath", "Enter")
    frame = page.frame_locator("#dashFrame")
    frame.locator("#dashboardSidebar").wait_for()
    # The frame is sandboxed without same-origin access, so the dashboard
    # cannot use local storage: it must still start and work.
    before = frame.locator("#dashboardSidebar").bounding_box()["width"]
    assert round(before) == 220
    handle = frame.locator("#sidebarSplitter").bounding_box()
    frame_left = page.locator("#dashFrame").bounding_box()["x"]
    page.mouse.move(handle["x"] + handle["width"] / 2, handle["y"] + 200)
    page.mouse.down()
    page.mouse.move(frame_left + 340, handle["y"] + 200, steps=6)
    page.mouse.up()
    assert round(frame.locator("#dashboardSidebar").bounding_box()["width"]) == 340
    frame.locator("#sidebarToggle").click()
    _wait_until(lambda: frame.locator("#dashboardSidebar").is_hidden())
    assert frame.locator("#sidebarToggle").get_attribute("aria-expanded") == "false"


def test_results_show_each_signatures_cosmic_split_and_closest_match(page, tmp_path):
    from SigProfilerExtractor.web import results

    catalogue, _ = results.cosmic_catalogue(96, {})
    if catalogue is None:
        pytest.skip("SigProfilerAssignment's COSMIC catalogue is not installed")
    rows = [line.split("\t") for line in catalogue.read_text().splitlines()]
    col = rows[0].index("SBS13")
    out = tmp_path / "out"
    sig = out / "SBS96" / "Suggested_Solution" / "SBS96_De-Novo_Solution" / "Signatures"
    sig.mkdir(parents=True)
    (sig / "SBS96_De-Novo_Signatures.txt").write_text(
        "MutationType\tSBS96A\n" + "".join(f"{r[0]}\t{r[col]}\n" for r in rows[1:]))
    cosmic = out / "SBS96" / "Suggested_Solution" / "COSMIC_SBS96_Decomposed_Solution"
    cosmic.mkdir(parents=True)
    (cosmic / "De_Novo_map_to_COSMIC_SBS96.csv").write_text(
        "De novo extracted, Global NMF Signatures, L1 Error %, L2 Error %, KL Divergence, Cosine Similarity, Correlation\n"
        "Signature 96-SBS96A, Signature SBS2 (40.00%) & Signature SBS13 (60.00%), 5, 4, 0.01, 0.99, 0.98\n")
    (out / "SBS96" / "All_solutions_stat.csv").write_text("Signatures,x\n1*,0.9\n")
    (out / "JOB_METADATA.txt").write_text("\topportunity_genome: GRCh37\n\tcosmic_version: 3.6\n")

    page.fill("#openPath", str(out))
    page.press("#openPath", "Enter")
    row = page.locator("#compareBody .cmp-row[data-signature='SBS96A']")
    row.wait_for()
    assert row.locator(".split-bar > span").count() == 2
    assert row.locator(".split-legend").text_content().replace("\xa0", " ") == "SBS13 60.0%SBS2 40.0%"
    _wait_text(row.locator(".split-fit"), "cosine 0.99")
    assert row.locator(".close-best b").text_content() == "SBS13"
    assert "cosine 1.00" in row.locator(".close-best .pill").text_content()
    assert "good" in row.locator(".close-best .pill").get_attribute("class")
    _wait_text(page.locator("#compareNote"), "COSMIC v3.6 SBS (GRCh37)")
    assert page.is_visible("#cosmicCard") is False  # the New run card, on another tab, is untouched
    assert "hidden" not in (page.get_attribute("#cosmicCard", "class") or "")
