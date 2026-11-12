"""What a run asks SigProfilerExtractor for: defaults, presets and validation.

The page sends a flat settings object; :func:`validate` turns it into the
keyword arguments of ``sigpro.sigProfilerExtractor`` or a list of plain
messages saying what to fix. The defaults are SigProfilerExtractor's own (a
test compares them with the function's signature), so a run with nothing
changed is the run the paper and the command line describe.

This module imports nothing heavy: the server answers with it before torch,
SigProfilerAssignment and the rest are ever loaded.
"""

from __future__ import annotations

from pathlib import Path

# Input types the Workbench offers (legacy "csv" and "matobj" are left out).
INPUT_TYPES = {
    "vcf": {"label": "Variant calls", "kind": "folder"},
    "matrix": {"label": "Mutation matrix", "kind": "file"},
    "bedpe": {"label": "Structural variants", "kind": "folder"},
    "seg": {"label": "Copy number", "kind": "file"},
}
SEG_CALLERS = ("ASCAT", "ASCAT_NGS", "SEQUENZA", "ABSOLUTE", "BATTENBERG", "FACETS", "PURPLE", "TCGA")
# Builds with COSMIC reference signatures (sigpro.py resets anything else to GRCh37).
COSMIC_GENOMES = ("GRCh37", "GRCh38", "mm9", "mm10", "mm39", "rn6", "rn7")
COSMIC_VERSIONS = (1, 2, 3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6)
# Contexts a VCF run can extract, in the order the page lists them.
VCF_CONTEXTS = ("SBS96", "SBS288", "SBS384", "SBS1536", "SBS4608", "DBS78", "ID83")
DEFAULT_VCF_CONTEXTS = ("SBS96", "DBS78", "ID83")
NMF_INITS = ("random", "nndsvd", "nndsvda", "nndsvdar", "nndsvd_min")
PRECISIONS = ("single", "double")
NORMALIZATIONS = ("gmm", "100X", "log2", "none")
CLUSTERING_DISTANCES = ("cosine", "correlation")

# sigProfilerExtractor's keyword defaults (input_type, output and input_data
# have none). tests/web/test_params.py checks these against its signature.
DEFAULTS = {
    "reference_genome": "GRCh37",
    "opportunity_genome": "GRCh37",
    "cosmic_version": 3.6,
    "context_type": "default",
    "exome": False,
    "minimum_signatures": 1,
    "maximum_signatures": 25,
    "nmf_replicates": 100,
    "resample": True,
    "batch_size": 1,
    "cpu": -1,
    "assignment_cpu": -1,
    "gpu": False,
    "nmf_init": "random",
    "precision": "single",
    "matrix_normalization": "gmm",
    "seeds": "random",
    "min_nmf_iterations": 10000,
    "max_nmf_iterations": 1000000,
    "nmf_test_conv": 10000,
    "nmf_tolerance": 1e-15,
    "nnls_add_penalty": 0.05,
    "nnls_remove_penalty": 0.01,
    "initial_remove_penalty": 0.05,
    "collapse_to_SBS96": True,
    "clustering_distance": "cosine",
    "export_probabilities": True,
    "make_decomposition_plots": True,
    "make_dashboard": True,
    "stability": 0.8,
    "min_stability": 0.2,
    "combined_stability": 1.0,
    "allow_stability_drop": False,
    "get_all_signature_matrices": False,
    "stop_after_extraction": False,
    "volume": None,
}

# A preset sets only how much searching a run does. "standard" is
# SigProfilerExtractor's published setting; "quick" is for a first look at a
# cohort in minutes, not for reporting.
PRESETS = {
    "quick": {
        "label": "Quick look",
        "description": "Ranks 1 to 5, 10 replicates each. Minutes, for a first look; not for publication.",
        "values": {"minimum_signatures": 1, "maximum_signatures": 5, "nmf_replicates": 10},
    },
    "standard": {
        "label": "Standard",
        "description": "SigProfilerExtractor's published setting: ranks 1 to 25, 100 replicates each. Can take hours.",
        "values": {"minimum_signatures": 1, "maximum_signatures": 25, "nmf_replicates": 100},
    },
}

_BOOLEANS = ("exome", "resample", "gpu", "collapse_to_SBS96", "export_probabilities",
             "make_decomposition_plots", "make_dashboard", "allow_stability_drop",
             "get_all_signature_matrices", "stop_after_extraction")


class ParamsError(ValueError):
    """Settings a run cannot start with; ``problems`` lists each one."""

    def __init__(self, problems: list[str]):
        super().__init__(" ".join(problems))
        self.problems = problems


def _bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _int(settings: dict, key: str, problems: list, label: str, minimum: int | None = None,
         allow: tuple = ()) -> int | None:
    raw = settings.get(key, DEFAULTS.get(key))
    try:
        value = int(raw)
        if str(raw).strip() not in (str(value), f"{value}.0") and not isinstance(raw, int):
            raise ValueError
    except (TypeError, ValueError):
        problems.append(f"{label} must be a whole number.")
        return None
    if value in allow:
        return value
    if minimum is not None and value < minimum:
        problems.append(f"{label} must be at least {minimum}.")
        return None
    return value


def _float(settings: dict, key: str, problems: list, label: str, low: float | None = None,
           high: float | None = None, above: float | None = None) -> float | None:
    raw = settings.get(key, DEFAULTS.get(key))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        problems.append(f"{label} must be a number.")
        return None
    if value != value:  # NaN
        problems.append(f"{label} must be a number.")
        return None
    if above is not None and not value > above:
        problems.append(f"{label} must be greater than {above:g}.")
        return None
    if low is not None and value < low or high is not None and value > high:
        problems.append(f"{label} must be between {low:g} and {high:g}.")
        return None
    return value


def _choice(settings: dict, key: str, options, problems: list, label: str):
    value = settings.get(key, DEFAULTS.get(key))
    if value not in options:
        problems.append(f"{label} must be one of: {', '.join(map(str, options))}.")
        return None
    return value


def seed_file_problem(path: str) -> str | None:
    """Why a seeds file would be refused (the rules of sigpro.read_seed_file), or None."""
    target = Path(path).expanduser()
    if not target.is_file():
        return f"The seeds file does not exist: {path}"
    try:
        lines = [line.rstrip("\n").split("\t") for line in target.read_text().splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError):
        return "The seeds file could not be read."
    if not lines or "Seed" not in lines[0]:
        return "The seeds file must have a 'Seed' column (tab-separated), like the Seeds.txt a run writes."
    column = lines[0].index("Seed")
    rows = lines[1:]
    if len(rows) != 1:
        return f"The seeds file must hold exactly one seed, found {len(rows)}."
    try:
        int(rows[0][column])
    except (IndexError, ValueError):
        return "The seed in the seeds file is not a whole number."
    return None


def validate(settings: dict, *, cuda_available: bool = False) -> dict:
    """Turn the page's settings into sigProfilerExtractor keyword arguments.

    Raises ParamsError listing every problem at once.
    """
    problems: list[str] = []
    kwargs: dict = {}

    input_type = settings.get("input_type")
    if input_type not in INPUT_TYPES:
        problems.append("Choose what kind of input this is.")
    input_data = str(settings.get("input_data") or "").strip()
    if not input_data:
        problems.append("Choose the input.")
    elif input_type in INPUT_TYPES:
        target = Path(input_data).expanduser()
        if INPUT_TYPES[input_type]["kind"] == "folder" and not target.is_dir():
            problems.append(f"The input must be a folder: {input_data}")
        elif INPUT_TYPES[input_type]["kind"] == "file" and not target.is_file():
            problems.append(f"The input must be a file: {input_data}")
    if input_type == "seg":
        caller = settings.get("seg_caller")
        if caller not in SEG_CALLERS:
            problems.append("Choose the copy-number caller that made the segmentation file.")
        else:
            kwargs["input_type"] = f"seg:{caller}"
    elif input_type in INPUT_TYPES:
        kwargs["input_type"] = input_type
    kwargs["input_data"] = input_data
    output = str(settings.get("output") or "").strip()
    if not output:
        problems.append("Choose the output folder.")
    kwargs["output"] = output

    # Genome and contexts.
    if input_type == "vcf":
        genome = str(settings.get("reference_genome") or "").strip()
        if not genome:
            problems.append("Choose the reference genome the calls were made against.")
        kwargs["reference_genome"] = genome
        contexts = settings.get("contexts") or list(DEFAULT_VCF_CONTEXTS)
        unknown = [c for c in contexts if c not in VCF_CONTEXTS]
        if unknown:
            problems.append(f"Unknown mutation context: {', '.join(unknown)}.")
        elif not contexts:
            problems.append("Choose at least one mutation context.")
        kwargs["context_type"] = ",".join(c for c in VCF_CONTEXTS if c in contexts)
        # For VCF input SigProfilerExtractor uses the reference genome for COSMIC too.
        kwargs["opportunity_genome"] = genome if genome in COSMIC_GENOMES else "GRCh37"
    else:
        kwargs["opportunity_genome"] = _choice(settings, "opportunity_genome", COSMIC_GENOMES,
                                               problems, "The COSMIC reference genome")

    # How many signatures to try, and how hard.
    low = _int(settings, "minimum_signatures", problems, "The smallest number of signatures", 1)
    high = _int(settings, "maximum_signatures", problems, "The largest number of signatures", 1)
    if low is not None and high is not None and low > high:
        problems.append("The smallest number of signatures cannot be larger than the largest.")
    kwargs["minimum_signatures"], kwargs["maximum_signatures"] = low, high
    kwargs["nmf_replicates"] = _int(settings, "nmf_replicates", problems, "NMF replicates", 1)

    # NMF engine.
    norm = str(settings.get("matrix_normalization", DEFAULTS["matrix_normalization"])).strip()
    if norm not in NORMALIZATIONS:
        try:
            if int(norm) <= 0 or str(int(norm)) != norm:
                raise ValueError
        except ValueError:
            problems.append("Matrix normalization must be gmm, 100X, log2, none or a positive whole number.")
    kwargs["matrix_normalization"] = norm
    kwargs["nmf_init"] = _choice(settings, "nmf_init", NMF_INITS, problems, "NMF initialization")
    kwargs["precision"] = _choice(settings, "precision", PRECISIONS, problems, "Precision")
    kwargs["clustering_distance"] = _choice(settings, "clustering_distance", CLUSTERING_DISTANCES,
                                            problems, "Clustering distance")
    lo_it = _int(settings, "min_nmf_iterations", problems, "Minimum NMF iterations", 1)
    hi_it = _int(settings, "max_nmf_iterations", problems, "Maximum NMF iterations", 1)
    if lo_it is not None and hi_it is not None and lo_it > hi_it:
        problems.append("Minimum NMF iterations cannot be more than the maximum.")
    kwargs["min_nmf_iterations"], kwargs["max_nmf_iterations"] = lo_it, hi_it
    kwargs["nmf_test_conv"] = _int(settings, "nmf_test_conv", problems, "Convergence test interval", 1)
    kwargs["nmf_tolerance"] = _float(settings, "nmf_tolerance", problems, "NMF tolerance", above=0)
    seeds = str(settings.get("seeds") or "random").strip()
    if seeds != "random":
        problem = seed_file_problem(seeds)
        if problem:
            problems.append(problem)
    kwargs["seeds"] = seeds

    # Choosing the solution.
    kwargs["stability"] = _float(settings, "stability", problems, "Average stability cutoff", 0, 1)
    kwargs["min_stability"] = _float(settings, "min_stability", problems, "Minimum stability cutoff", 0, 1)
    kwargs["combined_stability"] = _float(settings, "combined_stability", problems,
                                          "Combined stability cutoff", 0, 2)

    # COSMIC assignment.
    try:
        version = float(settings.get("cosmic_version", DEFAULTS["cosmic_version"]))
    except (TypeError, ValueError):
        version = None
    if version not in COSMIC_VERSIONS:
        problems.append(f"COSMIC version must be one of: {', '.join(map(str, COSMIC_VERSIONS))}.")
    kwargs["cosmic_version"] = version
    for key, label in (("nnls_add_penalty", "Add penalty"), ("nnls_remove_penalty", "Remove penalty"),
                       ("initial_remove_penalty", "Initial remove penalty")):
        kwargs[key] = _float(settings, key, problems, label, 0, 1)

    # Execution.
    kwargs["cpu"] = _int(settings, "cpu", problems, "CPUs", 1, allow=(-1,))
    kwargs["assignment_cpu"] = _int(settings, "assignment_cpu", problems, "Assignment CPUs", 1, allow=(-1,))
    gpu = _bool(settings.get("gpu", False))
    if gpu and not cuda_available:
        problems.append("No CUDA GPU is available on this computer, so the GPU cannot be used.")
    kwargs["gpu"] = gpu
    kwargs["batch_size"] = _int(settings, "batch_size", problems, "GPU batch size", 1)

    for key in _BOOLEANS:
        if key != "gpu":
            kwargs[key] = _bool(settings.get(key, DEFAULTS[key]))
    if input_type != "vcf":
        kwargs["exome"] = _bool(settings.get("exome", False))
    volume = str(settings.get("volume") or "").strip()
    kwargs["volume"] = volume or None

    if problems:
        raise ParamsError(problems)
    return kwargs


def ranks(minimum: int, maximum: int, samples: int | None = None) -> int:
    """How many numbers of signatures a run tries (SigProfilerExtractor caps both
    ends at the number of samples)."""
    if samples:
        minimum, maximum = min(minimum, samples), min(maximum, samples)
    return max(0, maximum - minimum + 1)


def effort(kwargs: dict, contexts: int, samples: int | None = None) -> dict:
    """The NMF fits a run makes: contexts x ranks x replicates."""
    n_ranks = ranks(kwargs["minimum_signatures"], kwargs["maximum_signatures"], samples)
    return {"contexts": contexts, "ranks": n_ranks, "replicates": kwargs["nmf_replicates"],
            "fits": contexts * n_ranks * kwargs["nmf_replicates"]}


def page_settings() -> dict:
    """Everything the run form needs to draw its fields and presets."""
    return {
        "defaults": DEFAULTS,
        "presets": PRESETS,
        "input_types": INPUT_TYPES,
        "seg_callers": SEG_CALLERS,
        "cosmic_genomes": COSMIC_GENOMES,
        "cosmic_versions": COSMIC_VERSIONS,
        "vcf_contexts": VCF_CONTEXTS,
        "default_vcf_contexts": DEFAULT_VCF_CONTEXTS,
        "nmf_inits": NMF_INITS,
        "precisions": PRECISIONS,
        "normalizations": NORMALIZATIONS,
        "clustering_distances": CLUSTERING_DISTANCES,
    }
