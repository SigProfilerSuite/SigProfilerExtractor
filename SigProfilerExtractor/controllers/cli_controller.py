import argparse
from typing import List
from SigProfilerExtractor import sigpro


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "y", "1"):
        return True
    elif v.lower() in ("no", "false", "f", "n", "0"):
        return False
    else:
        raise argparse.ArgumentTypeError("Boolean value expected.")


def parse_arguments_extractor(args: List[str], description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)

    # Core required arguments
    input_type_help = (
        "The input file type: 'vcf', 'matrix', 'bedpe', or 'seg:TYPE'. "
        "Accepted callers for TYPE: {'ASCAT', 'ASCAT_NGS', 'SEQUENZA', "
        "'ABSOLUTE', 'BATTENBERG', 'FACETS', 'PURPLE', 'TCGA'}."
    )

    parser.add_argument(
        "input_type",
        help=input_type_help,
    )

    parser.add_argument(
        "output",
        help="Path to the output folder.",
    )

    input_data_help = (
        "Path to input data. For 'vcf' or 'bedpe', provide an input folder. "
        "For 'matrix' or 'seg:TYPE', provide an input file."
    )

    parser.add_argument(
        "input_data",
        help=input_data_help,
    )

    # Optional arguments with defaults
    parser.add_argument(
        "--reference_genome",
        default="GRCh37",
        help="Reference genome (default: 'GRCh37'). This parameter is applicable only if the input_type is 'vcf'.",
    )
    parser.add_argument(
        "--opportunity_genome",
        default="GRCh37",
        help="The build or version of the reference genome for the reference signatures (default: 'GRCh37'). When the input type is 'vcf' the value for 'opportunity_genome' will be used instead.",
    )
    parser.add_argument(
        "--context_type",
        default="default",
        help="Mutational context types (default: '96,DINUC,ID').",
    )
    parser.add_argument(
        "--exome",
        type=str2bool,
        nargs="?",
        const=True,
        default=False,
        help="Extract exomes (default: False).",
    )
    parser.add_argument(
        "--minimum_signatures",
        type=int,
        default=1,
        help="Minimum number of signatures to be extracted (default: 1).",
    )
    parser.add_argument(
        "--maximum_signatures",
        type=int,
        default=10,
        help="Maximum number of signatures to be extracted (default: 10).",
    )
    parser.add_argument(
        "--nmf_replicates",
        type=int,
        default=100,
        help="Number of NMF replicates to be performed at each rank using W and H (default: 100).",
    )
    parser.add_argument(
        "--resample",
        type=str2bool,
        nargs="?",
        const=True,
        default=True,
        help="Add poisson noise to samples by resampling (default: True).",
    )
    parser.add_argument(
        "--seeds",
        default="random",
        help="Seeds for reproducible resamples, file path or 'random' (default: 'random').",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=1,
        help="Batch size is for GPU only and defines the number of NMF replicates to be performed by each CPU during parallel processing (default: 1).",
    )
    parser.add_argument(
        "--cpu",
        type=int,
        default=-1,
        help="Number of processors to use (default: all available).",
    )
    parser.add_argument(
        "--assignment_cpu",
        type=int,
        default=-1,
        help="Number of processors to be used by SigProfilerAssignment for the final signature assignment step (default: all available). This is independent of the 'cpu' parameter.",
    )
    parser.add_argument(
        "--gpu",
        type=str2bool,
        nargs="?",
        const=True,
        default=False,
        help="Use GPU if available (default: False). note: All available CPU processors are used by default, which may cause a memory error. This error can be resolved by reducing the number of CPU processes through the 'cpu' parameter.",
    )
    parser.add_argument(
        "--nmf_init",
        default="random",
        help="The initialization algorithm for W and H matrix of NMF (default: 'random'). Options are 'random', 'nndsvd', 'nndsvda', 'nndsvdar' and 'nndsvd_min'.",
    )
    parser.add_argument(
        "--precision",
        default="single",
        help="Precision for calculations (default: 'single'). Options are 'single' and 'double'.",
    )
    parser.add_argument(
        "--matrix_normalization",
        default="gmm",
        help="Method of normalizing the genome matrix before it is analyzed by NMF (default: 'gmm'). Options are 'custom', 'gmm', 'log2', or 'none'.",
    )
    parser.add_argument(
        "--min_nmf_iterations",
        type=int,
        default=10000,
        help="Minimum NMF iterations (default: 10000).",
    )
    parser.add_argument(
        "--max_nmf_iterations",
        type=int,
        default=1000000,
        help="Maximum NMF iterations (default: 1000000).",
    )
    parser.add_argument(
        "--nmf_test_conv",
        type=int,
        default=10000,
        help="Test convergence every X iterations (default: 10000).",
    )
    parser.add_argument(
        "--nmf_tolerance",
        type=float,
        default=1e-15,
        help="NMF tolerance for convergence (default: 1e-15).",
    )
    parser.add_argument(
        "--get_all_signature_matrices",
        type=str2bool,
        nargs="?",
        const=True,
        default=False,
        help="Get all NMF matrices (default: False).",
    )
    parser.add_argument(
        "--export_probabilities",
        type=str2bool,
        nargs="?",
        const=True,
        default=True,
        help="Export probability matrix (default: True).",
    )
    parser.add_argument(
        "--stability",
        type=float,
        default=0.8,
        help="Average stability cutoff (default: 0.8).",
    )
    parser.add_argument(
        "--min_stability",
        type=float,
        default=0.2,
        help="Minimum stability cutoff (default: 0.2).",
    )
    parser.add_argument(
        "--combined_stability",
        type=float,
        default=1.0,
        help="Combined stability cutoff (default: 1.0).",
    )
    parser.add_argument(
        "--allow_stability_drop",
        type=str2bool,
        nargs="?",
        const=True,
        default=False,
        help="Allow stability drop (default: False).",
    )
    parser.add_argument(
        "--cosmic_version",
        type=float,
        default=sigpro.DEFAULT_COSMIC_VERSION,
        help=(
            "COSMIC version for reference signatures. Valid values are "
            f"{', '.join(map(str, sigpro.SUPPORTED_COSMIC_VERSIONS))} "
            f"(default: {sigpro.DEFAULT_COSMIC_VERSION})."
        ),
    )
    parser.add_argument(
        "--make_decomposition_plots",
        type=str2bool,
        nargs="?",
        const=True,
        default=True,
        help="Generate decomposition plots (default: True).",
    )
    parser.add_argument(
        "--collapse_to_SBS96",
        type=str2bool,
        nargs="?",
        const=True,
        default=True,
        help="Collapse to SBS288 and SBS1536 matrices to SBS96. If False, will map reference signatures to the same context as input (default: True).",
    )

    parser.add_argument(
        "--stop_after_extraction",
        type=str2bool,
        nargs="?",
        const=True,
        default=False,
        help="Stop after de novo extraction (default: False).",
    )

    parser.add_argument(
        "--volume",
        default=None,
        help="User specified directory for saving/loading template files.",
    )

    return parser.parse_args(args)


class CliController:
    def dispatch_sigProfilerExtractor(self, user_args: List[str]) -> None:
        parsed_args = parse_arguments_extractor(
            user_args, "Extract mutational signatures from input samples."
        )
        sigpro.sigProfilerExtractor(
            input_type=parsed_args.input_type,
            output=parsed_args.output,
            input_data=parsed_args.input_data,
            reference_genome=parsed_args.reference_genome,
            opportunity_genome=parsed_args.opportunity_genome,
            context_type=parsed_args.context_type,
            exome=parsed_args.exome,
            minimum_signatures=parsed_args.minimum_signatures,
            maximum_signatures=parsed_args.maximum_signatures,
            nmf_replicates=parsed_args.nmf_replicates,
            resample=parsed_args.resample,
            seeds=parsed_args.seeds,
            batch_size=parsed_args.batch_size,
            cpu=parsed_args.cpu,
            assignment_cpu=parsed_args.assignment_cpu,
            gpu=parsed_args.gpu,
            nmf_init=parsed_args.nmf_init,
            precision=parsed_args.precision,
            matrix_normalization=parsed_args.matrix_normalization,
            min_nmf_iterations=parsed_args.min_nmf_iterations,
            max_nmf_iterations=parsed_args.max_nmf_iterations,
            nmf_test_conv=parsed_args.nmf_test_conv,
            nmf_tolerance=parsed_args.nmf_tolerance,
            get_all_signature_matrices=parsed_args.get_all_signature_matrices,
            export_probabilities=parsed_args.export_probabilities,
            stability=parsed_args.stability,
            min_stability=parsed_args.min_stability,
            combined_stability=parsed_args.combined_stability,
            allow_stability_drop=parsed_args.allow_stability_drop,
            cosmic_version=parsed_args.cosmic_version,
            make_decomposition_plots=parsed_args.make_decomposition_plots,
            collapse_to_SBS96=parsed_args.collapse_to_SBS96,
            stop_after_extraction=parsed_args.stop_after_extraction,
            volume=parsed_args.volume,
        )
