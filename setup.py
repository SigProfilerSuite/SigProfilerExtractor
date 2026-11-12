from pathlib import Path

from setuptools import find_namespace_packages, setup


LONG_DESCRIPTION = Path("README.md").read_text(encoding="utf-8")

INSTALL_REQUIRES = [
    "scipy>=1.6.3",
    "torch>=1.8.1",
    "numpy>=2.0.0",
    "pandas>=2.0.0",
    "sigProfilerPlotting>=1.5.0",  # Interactive renderer used by reports.html
    "SigProfilerMatrixGenerator>=1.3.5",
    "SigProfilerAssignment>=1.1.5",
    "statsmodels>=0.9.0",
    "scikit-learn>=0.24.2",
    "psutil>=5.6.1",
]

VERSION_TEMPLATE = "version = '{version}'\n"


setup(
    name="SigProfilerExtractor",
    use_scm_version={
        "write_to": "SigProfilerExtractor/_version.py",
        "write_to_template": VERSION_TEMPLATE,
        "fallback_version": "0+unknown",
    },
    description="Extracts mutational signatures from mutational catalogues",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="https://github.com/SigProfilerSuite/SigProfilerExtractor.git",
    author="S Mishu Ashiqul Islam",
    author_email="m0islam@ucsd.edu",
    license="UCSD",
    packages=find_namespace_packages(include=["SigProfilerExtractor*"]),
    install_requires=INSTALL_REQUIRES,
    extras_require={
        # Browser tests of the Workbench (tests/web/test_web_interactions.py).
        "web-tests": ["pytest", "playwright"],
    },
    include_package_data=True,
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "SigProfilerExtractor=SigProfilerExtractor.sigprofilerextractor_cli:main_function",
            "sigprofilerextractor-web=SigProfilerExtractor.web.launcher:main",
        ],
    },
    zip_safe=False,
)
