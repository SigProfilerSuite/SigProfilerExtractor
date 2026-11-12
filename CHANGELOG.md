
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.6.1] - 2026-11-11

### Changed
- The Workbench launcher installs its dependencies with [uv](https://docs.astral.sh/uv/) when it can: the `uv` on PATH, or uv added to the Workbench's own environment. On a Mac this cut a first install from 95 s to 59 s and a reinstall from 45 s to 4 s. It falls back to pip if uv cannot be added or cannot install; set `SPE_WEB_INSTALLER=pip` to always use pip.

### Fixed
- VCF and BEDPE input now work on Windows, from Python, the command line and the Workbench. The project name was taken by splitting the input path on `/`, so a Windows path stayed whole, and SigProfilerMatrixGenerator's log file name then contained its `:` (`OSError: [Errno 22] Invalid argument`). The name is now the input folder's own name, found with the platform's path rules.
- Workbench runs on Windows no longer fail with `UnicodeEncodeError` when SigProfilerAssignment draws its progress bars. Output written to a file used the Windows code page (such as cp1252), which has no block characters; each run now writes its output as UTF-8.
- The Workbench's run log on Windows shows its lines. Lines ending in `\r\n` were taken for progress-bar redraws and shown blank.
- Checking whether a process is still running no longer sends Ctrl+C to the console on Windows, where `os.kill(pid, 0)` sends `CTRL_C_EVENT`. This could interrupt `launch_web.bat --stop`.
- The run log no longer garbles a character that is split between two reads of the log.
- A zip or tarball of the repository downloaded from GitHub knows its version (`.git_archival.txt`). Without git history it was `0+unknown`, and the Workbench showed "v0"; it now shows nothing if the version cannot be found.

## [1.6.0] - 2026-11-11

### Added
- Add the SigProfilerExtractor Workbench, a local web app for running extractions without writing code. Start it with `SigProfilerExtractor web`, `sigprofilerextractor-web`, or the double-click launchers (`launch_web.command` on macOS, `launch_web.bat` on Windows); the first launch sets up its own environment. It runs from VCFs, a mutation matrix, structural-variant BEDPE files, or copy-number segments, checks the input before anything runs, offers Quick look and Standard presets with a live estimate of the work, follows each run's progress, and shows the suggested solution, how each de novo signature splits into COSMIC signatures and its closest COSMIC signature by cosine similarity, the interactive dashboard, and every PDF plot and table. It listens only on this computer and protects every change with a per-launch token. See the Graphical Interface page of the documentation.
- Add double-click uninstallers (`uninstall_web.command` on macOS, `uninstall_web.bat` on Windows) that remove the Workbench's environment and run records but never results.
- Add the `web-tests` extra for the Workbench's browser tests.
- Generate a self-contained `reports.html` after extraction. The offline dashboard provides interactive overview, all-rank signatures, selected de novo and COSMIC solutions, sample activities, and per-rank statistics using SigProfilerPlotting's context-aware Plotly renderers.
- Add the `make_dashboard` Python and CLI option (default: `True`) to disable dashboard generation when needed.
- Add contextual information buttons to every dashboard figure, with guidance on its axes, metrics, interpretation, and source data.

### Changed
- Require SigProfilerPlotting 1.5.0 or newer for its validated matrix loader and interactive rendering API.
- Refine the dashboard with separate stability and reconstruction panels, selected-rank evidence, cohort mutation summaries, single-metric statistics plots, activity ordering and log-color controls, a color-vision-friendly heatmap, accessible table sorting, bookmarkable view URLs, and a side panel that can be resized or hidden.

## [1.5.0] - 2026-09-28

### Changed
- Updated the default COSMIC reference signature version from 3.5 to 3.6.
- Updated the minimum SigProfilerAssignment version to 1.1.5 for COSMIC v3.6 support.
- Changed the CLI default for `--maximum_signatures` from 10 to 25 so it matches the Python API.
- GPU batches now give every NMF replicate its own resampling and initialization generators, sample totals, and convergence stopping point, matching CPU and single-replicate GPU behavior.
- A seeds file now contains exactly one root seed. All random generators used by a run are derived reproducibly from that seed.
- Existing results for a mutation context are moved to `<context>_previous_<timestamp>` before a rerun writes new results, preventing files from different runs from being mixed.
- Importing SigProfilerExtractor no longer suppresses warnings globally or changes the host program's multiprocessing start method.

### Fixed
- Added a lower bound (1e-16) to W, H and W @ H in the KL multiplicative updates, on CPU and GPU. A multiplicative update cannot move an entry away from exactly zero, so zeros from the NNDSVD initialization (about half of W and H) or from underflow stayed zero for the whole run. The fit could then stall and pass the convergence test early at a worse solution; with `nmf_init="nndsvd"` this could happen at the first allowed convergence check. Results and run times can change, including with the default random initialization.
- Fixed the KL loss returning NaN when the matrix passed to NMF contains a zero (`0 * log 0`). The extraction pipeline raises every value to at least 1e-4 before NMF, so this affected only direct use of `nmf_cpu` and `nmf_gpu`.
- If a cell of W @ H reached zero, the update produced inf or NaN that spread to all of W and H with no error. An NMF replicate whose W or H contains NaN or inf now raises `FloatingPointError` instead of entering clustering.
- CPU extraction now runs the requested number of NMF replicates when `batch_size` is greater than 1. The setting only controls GPU batching.
- Forwarded `nnls_add_penalty`, `nnls_remove_penalty`, `initial_remove_penalty`, and `collapse_to_SBS96` to SigProfilerAssignment.
- Recomputed the signature-rank range for each mutation context so a context with fewer samples cannot narrow the range used by subsequent contexts.
- Seeded the Gaussian mixture model used to choose the normalization cutoff, making it reproducible from `Seeds.txt`.
- Stopped treating failed silhouette calculations as perfect stability. Rank one remains stable by convention; invalid higher-rank calculations now raise a clear error.
- Removed two unused per-replicate arrays that could each consume several gigabytes for large mutation matrices.
- Validated `matrix_normalization`. Accepted values are `"gmm"`, `"100X"`, `"log2"`, `"none"`, or a positive integer cutoff; unsupported values now raise `ValueError`.
- Samples containing some missing values now raise a clear error instead of being dropped silently. Completely empty columns and samples with zero mutations are reported and removed.
- Preserved input values as float64 throughout NMF when `precision="double"` is selected.
- Labelled matrices with unrecognized channel counts as `CH<n>` instead of incorrectly labelling every such matrix as SBS.
- Fixed loading `Seeds.txt` with current NumPy versions and added clear validation for a missing `Seed` column or more than one root seed.
- A run now raises an error instead of reporting success when none of the requested mutation contexts can be analyzed.
- Rounded exported NMF activities to the nearest integer instead of truncating them.
- Made the `SV_Matrices` output location independent of whether a BEDPE input directory has a trailing slash.
- Unified CPU and GPU per-replicate diagnostics so both paths calculate them from the matrix actually fitted by NMF.

## [1.2.7] - 2026-01-22

### Fixed
- Fixed NumPy 2.0 compatibility issue by removing the `nimfa` dependency, which was incompatible with NumPy 2.0 due to use of deprecated `np.mat()` function.
- Fixed pandas 3.12 compatibility issues:
  - Updated `to_csv()` calls to use `sep` as keyword argument instead of positional argument
  - Fixed `set_index()` calls to work with pandas 3.12's stricter type checking by converting StringArray to list
  - Fixed `iloc` assignment for string conversion operations
  - Fixed Series indexing to use `.iloc[0]` for positional access instead of `[0]` for label-based access
- Fixed compatibility issues in SigProfilerAssignment and SigProfilerPlotting packages for pandas 3.12

### Changed
- Removed `nimfa` dependency and implemented NNDSVD initialization directly in the codebase.
- Updated `sigProfilerPlotting` dependency to >=1.4.3 for pandas 3.12 compatibility.
- Removed TMB debug file output.
- Migrated CI/CD pipeline from Travis CI to GitHub Actions for improved reliability and modern workflow management.

### Added
- Added `SigProfilerExtractor/nndsvd.py` with standalone NNDSVD implementation supporting all variants (nndsvd, nndsvda, nndsvdar, nndsvd_min).

## [1.2.6] - 2026-01-06

### Changed
- Updated default COSMIC version from 3.4 to 3.5. Added support for COSMIC v3.5 signatures in the `cosmic_version` parameter.
- Updated SigProfilerAssignment dependency requirement from >=1.0.1 to >=1.1.0 to support COSMIC v3.5 signatures.

## [1.2.5] - 2025-10-28

### Added
- Implemented a CI/CD pipeline with Travis CI to automate the building and publishing of Docker images to Docker Hub.
- Added a Dockerfile to the repository for containerization. Documentation on how to use the Dockerfile needs to be added to the README.

## [1.2.4] - 2025-10-20

### Added
- Added the `assignment_cpu` parameter to independently control the number of CPU cores used for the signature assignment step. This change enables full support for the parallel processing enhancements in **SigProfilerAssignment v1.0.0**, allowing for significant performance improvements and more granular resource control.

## [1.2.3] - 2025-09-19

### Added
- Added support for rn7 and mm39 genomes in SigProfilerExtractor.

## [1.2.2] - 2025-08-11

### Added
- Added mutation count and stability to 4608 plots in All_Solutions
- Add a stop parameter to the CLI to stop after de novo extraction.

## [1.2.1] - 2025-05-14

### Fixed
- Fixed an issue where the CLI was returning a non-zero exit code when the `--help` flag was passed.

 ### Added
- Added `pyproject.toml` for modern Python packaging support.

## [1.2.0] - 2025-02-11

### Changed
- Updated dependencies: Now requires **Pandas >= 2.0.0**, **NumPy >= 2.0.0**, and **Python >= 3.9**.
- Dropped support for **Python 3.8**
- **Intel-based MacBooks are no longer supported** due to upstream changes in **PyTorch**, which has dropped support for macOS x86_64. Users with Intel-based MacBooks will need to migrate to Apple Silicon (M1/M2) or use a Linux-based development environment.

## [1.1.25] - 2024-12-09

### Added
- Introduced a Command-Line Interface (CLI) for SigProfilerExtractor, enabling users to interact with the tool via terminal commands.

### Updated
- Improved the formatting of the parameter table for sigProfilerExtractor function for better readability and consistency.
- The CI/CD badge link has been fixed.
