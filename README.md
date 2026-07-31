[![Docs](https://img.shields.io/badge/docs-latest-blue.svg)](https://sigprofilersuite.github.io/SigProfilerExtractor/)
[![License](https://img.shields.io/badge/License-BSD\%202--Clause-orange.svg)](https://opensource.org/licenses/BSD-2-Clause)
[![CI](https://github.com/SigProfilerSuite/SigProfilerExtractor/actions/workflows/ci.yml/badge.svg)](https://github.com/SigProfilerSuite/SigProfilerExtractor/actions/workflows/ci.yml)

# SigProfilerExtractor
SigProfilerExtractor allows de novo extraction of mutational signatures from data generated in a matrix format. 
The tool identifies the number of operative mutational signatures, their activities in each sample, and the probability 
for each signature to cause a specific mutation type in a cancer sample. The tool makes use of SigProfilerMatrixGenerator 
and SigProfilerPlotting.

## Documentation

Full documentation is available in `docs/` (rendered via MkDocs): https://sigprofilersuite.github.io/SigProfilerExtractor/

# Table of contents
- [Installation](#installation)
- [Functions](#functions)
  - [importdata](#importdata)
  - [sigProfilerExtractor](#sigProfilerExtractor)
  - [estimate_solution](#estimate_solution)
  - [decompose](#decompose)
  - [PlotActivity.py](#plotActivity)
- [Video Tutorials](#video_tutorials)
- [Citation](#citation)
- [Copyright](#copyright)
- [Contact Information](#contact)


## <a name="installation"></a> Installation

To install the current version of this Github repo, git clone this repo or download the zip file.
Unzip the contents of SigProfilerExtractor-master.zip or the zip file of a corresponding branch.

In the command line, please run the following:
```bash
$ cd SigProfilerExtractor-master
$ pip install .
```

For most recent stable pypi version of this tool,
In the command line, please run the following:
```bash
$ pip install SigProfilerExtractor
```

Install your desired reference genome from the command line/terminal as follows (available reference genomes are: GRCh37, GRCh38, mm9, and mm10):
```python
$ python
from SigProfilerMatrixGenerator import install as genInstall
genInstall.install('GRCh37')
```

This will install the human 37 assembly as a reference genome. You may install as many genomes as you wish.

Next, open a python interpreter and import the SigProfilerExtractor module. Please see the examples of the functions. 

## <a name="functions"></a> Functions
The list of available functions are:
- importdata
- sigProfilerExtractor
- estimate_solution
- decompose

And an additional script:
- plotActivity.py

### <a name="importdata"></a> importdata
Imports the path of example data.

```python
importdata(datatype="matrix")
```

#### importdata Example

```python 
from SigProfilerExtractor import sigpro as sig
path_to_example_table = sig.importdata("matrix")
data = path_to_example_table 
# This "data" variable can be used as a parameter of the "project" argument of the sigProfilerExtractor function.

# To get help on the parameters and outputs of the "importdata" function, please use the following:
help(sig.importdata)
```

### <a name="sigProfilerExtractor"></a> sigProfilerExtractor
    
Extracts mutational signatures from an array of samples.

```python 
sigProfilerExtractor(input_type, out_put, input_data, reference_genome="GRCh37", opportunity_genome = "GRCh37", cosmic_version=3.6, context_type = "default", exome = False,
                         minimum_signatures=1, maximum_signatures=10, nmf_replicates=100, resample = True, batch_size=1, cpu=-1, gpu=False, 
                         nmf_init="random", precision= "single", matrix_normalization= "gmm", seeds= "random", 
                         min_nmf_iterations= 10000, max_nmf_iterations=1000000, nmf_test_conv= 10000, nmf_tolerance= 1e-15, get_all_signature_matrices= False)
```

| Category | Parameter | Variable Type | Parameter Description |
| --------- | --------------------- | -------- |-------- |
| **Input Data** |  |  | |
|  | **input_type** | String | The type of input:<br><ul><li>`"vcf"`: used for vcf format inputs.</li><li>`"matrix"`: used for table format inputs using a tab separated file.</li><li>`"bedpe"`: used for bedpe files with each SV annotated with its type, size bin, and clustered/non-clustered status. Please check the required format at https://github.com/SigProfilerSuite/SigProfilerMatrixGenerator#structural-variant-matrix-generation.</li><li>`"seg:TYPE"`: used for a multi-sample segmentation file for copy number analysis. Please check the required format at https://github.com/SigProfilerSuite/SigProfilerMatrixGenerator#copy-number-matrix-generation. The accepted callers for TYPE are the following {"ASCAT", "ASCAT_NGS", "SEQUENZA", "ABSOLUTE", "BATTENBERG", "FACETS", "PURPLE", "TCGA"}. For example, when using segmentation file from BATTENBERG then set input_type to "seg:BATTENBERG".</li></ul> |
|  | **output** | String | The name of the output folder. The output folder will be generated in the current working directory.  |
|  | **input_data** | String | <br>Path to input folder for input_type:<ul><li>`vcf`</li><li>`bedpe`</li></ul>Path to file for input_type:<ul><li>`matrix`</li><li>`seg:TYPE`</li></ul> |
|  | **reference_genome** | String | The name of the reference genome (default: `"GRCh37"`). This parameter is applicable only if the `input_type` is `"vcf"`. |
|  | **opportunity_genome** | String | The build or version of the reference genome for the reference signatures (default: `"GRCh37"`). When the input_type is `"vcf"`, the opportunity_genome automatically matches the input reference genome value. Only the genomes available in COSMIC are supported (`GRCh37`, `GRCh38`, `mm9`, `mm10`, `mm39`, `rn6`, and `rn7`). If a different opportunity genome is selected, the default genome `GRCh37` will be used. |
|  | **context_type** | String | Mutation context name(s), separated by commas (`,`), that define the mutational contexts for signature extraction (default: `"96,DINUC,ID"`). In the default value, `96` represents the SBS96 context, `DINUC` represents the dinucleotide context, and `ID` represents the indel context. |
|  | **exome** | Boolean | Defines if the exomes will be extracted (default: `False`). |
| **NMF Replicates** |  |  |  | 
|  | **minimum_signatures** | Positive Integer | The minimum number of signatures to be extracted (default: `1`). |
|  | **maximum_signatures** | Positive Integer | The maximum number of signatures to be extracted (default: `25`). |
|  | **nmf_replicates** | Positive Integer | The number of iteration to be performed to extract each number signature (default: `100`). |
|  | **resample** | Boolean | If `True`, add poisson noise to samples by resampling (default: `True`). |
|  | **seeds** | String | Ensures reproducible NMF replicate resamples. Provide the path to the `Seeds.txt` file (found in the results folder from a previous analysis) to reproduce results (default: `"random"`). |
| **NMF Engines** |  |  |  | 
|  | **matrix_normalization** | String | Method of normalizing the genome matrix before it is analyzed by NMF (default: `"gmm"`). Options are, `"log2"`, `"custom"` or `"none"`. |
|  | **nmf_init** | String | The initialization algorithm for W and H matrix of NMF (default: `"random"`). Options are `"random"`, `"nndsvd"`, `"nndsvda"`, `"nndsvdar"` and `"nndsvd_min"`. |
|  | **precision** | String | Values should be single or double (default: `"single"`). |
|  | **min_nmf_iterations** | Integer | Value defines the minimum number of iterations to be completed before NMF converges (default: `10000`). |
|  | **max_nmf_iterations** | Integer | Value defines the maximum number of iterations to be completed before NMF converges (default: `1000000`). |
|  | **nmf_test_conv** | Integer | Value defines the number number of iterations to done between checking next convergence (default: `10000`). |
|  | **nmf_tolerance** | Float | Value defines the tolerance to achieve to converge (default: `1e-15`).|
| **Execution** |  |  |  | 
|  | **cpu** | Integer | The number of processors to be used to extract the signatures (default: all processors). |
|  | **assignment_cpu** | Integer | Number of processors to be used by SigProfilerAssignment for the final signature assignment step (default: all available). This is independent of the `cpu` parameter. |
|  | **gpu** | Boolean | Defines if the GPU resource will used if available (default: `False`). If `True`, the GPU resources will be used in the computation. *Note: All available CPU processors are used by default, which may cause a memory error. This error can be resolved by reducing the number of CPU processes through the `cpu` parameter.*|
|  | **batch_size** | Integer | Will be effective only if the GPU is used. Defines the number of NMF replicates to be performed by each CPU during the parallel processing (default: `1`). *Note: For `batch_size` values greater than 1, each NMF replicate will update until `max_nmf_iterations` is reached.*|
| **Solution Estimation Thresholds** |  |  |  | 
|  | **stability** | Float | The cutoff thresh-hold of the average stability (default: `0.8`). Solutions with average stabilities below this thresh-hold will not be considered. |
|  | **min_stability** | Float | The cutoff thresh-hold of the minimum stability (default: `0.2`). Solutions with minimum stabilities below this thresh-hold will not be considered.  |
|  | **combined_stability** | Float | The cutoff thresh-hold of the combined stability (sum of average and minimum stability) (default: `1.0`). Solutions with combined stabilities below this thresh-hold will not be considered. |
|  | **allow_stability_drop** | Boolean | Defines if solutions with a drop in stability with respect to the highest stable number of signatures will be considered (default: `False`). |
| **Decomposition** |  |  |  | 
|  | **cosmic_version** | Float | Defines the version of the COSMIC reference signatures (default: `3.6`). Takes a positive float among `1`, `2`, `3`, `3.1`, `3.2`, `3.3`, `3.4`, `3.5`, and `3.6`.|
|  | **make_decomposition_plots** | Boolean | Generate de novo to COSMIC signature decomposition plots as part of the results (default: `True`). Set to `False` to skip generating these plots. |
|  | **collapse_to_SBS96** | Boolean | If `True`, SBS288 and SBS1536 de novo signatures will be mapped to SBS96 reference signatures (default: `True`). If `False`, those will be mapped to reference signatures of the same context.
| **Others** |  |  |  | 
|  | **get_all_signature_matrices** | Boolean | Write to output Ws and Hs from all the NMF iterations (default: `False`) |
|  | **export_probabilities** | Boolean | Create the probability matrix (default: `True`). |
|  | **volume** | String | Path to the volume for writing and loading reference genomes, plotting templates, and COSMIC signature plots (default: `None`). Environmental variables take precedence: `SIGPROFILERMATRIXGENERATOR_VOLUME`, `SIGPROFILERPLOTTING_VOLUME`, and `SIGPROFILERASSIGNMENT_VOLUME`. |
    
#### sigProfilerExtractor Example
VCF Files as Input
```python    
from SigProfilerExtractor import sigpro as sig
def main_function():
    # to get input from vcf files
    path_to_example_folder_containing_vcf_files = sig.importdata("vcf")
    # you can put the path to your folder containing the vcf samples
    data = path_to_example_folder_containing_vcf_files
    sig.sigProfilerExtractor("vcf", "example_output", data, minimum_signatures=1, maximum_signatures=3)
if __name__=="__main__":
   main_function()
# Wait until the excecution is finished. The process may a couple of hours based on the size of the data.
# Check the current working directory for the "example_output" folder.
```
Matrix File as Input
```python
from SigProfilerExtractor import sigpro as sig
def main_function():    
   # to get input from table format (mutation catalog matrix)
   path_to_example_table = sig.importdata("matrix")
   data = path_to_example_table # you can put the path to your tab delimited file containing the mutational catalog matrix/table
   sig.sigProfilerExtractor("matrix", "example_output", data, opportunity_genome="GRCh38", minimum_signatures=1, maximum_signatures=3)
if __name__=="__main__":
   main_function()
```

#### sigProfilerExtractor Output
To learn about the output, see `docs/output.md`.
  

### <a name="estimate_solution"></a> Estimation of the Optimum Solution
Estimate the optimum solution (rank) among different number of solutions (ranks). 

```python
estimate_solution(base_csvfile="All_solutions_stat.csv", 
          All_solution="All_Solutions", 
          genomes="Samples.txt", 
          output="results", 
          title="Selection_Plot",
          stability=0.8, 
          min_stability=0.2, 
          combined_stability=1.0,
          allow_stability_drop=False,
          exome=False)
```  
    
| Parameter | Variable Type | Parameter Description |
| --------------------- | -------- |-------- |
| **base_csvfile** | String | Default is `"All_solutions_stat.csv"`. Path to a CSV file that contains the statistics of all solutions. |
| **All_solution** | String | Default is `"All_Solutions"`. Path to a folder that contains the results of all solutions. |
| **genomes** | String | Default is `"Samples.txt"`. Path to a tab delimilted file that contains the mutation counts for all genomes given to different mutation types. |
| **output** | String | Default is `"results"`. Path to the output folder. |
| **title** | String | Default is `"Selection_Plot"`. This sets the title of the selection_plot.pdf |
| **stability** | Float | Default is 0.8. The cutoff thresh-hold of the average stability. Solutions with average stabilities below this thresh-hold will not be considered. |
| **min_stability** | Float | Default is `0.2`. The cutoff thresh-hold of the minimum stability. Solutions with minimum stabilities below this thresh-hold will not be considered. |
| **combined_stability** | Float | Default is `1.0`. The cutoff thresh-hold of the combined stability (sum of average and minimum stability). Solutions with combined stabilities below this thresh-hold will not be considered. |
| **allow_stability_drop** | Boolean | Default is `False`. Defines if solutions with a drop in stability with respect to the highest stable number of signatures will be considered. |
| **exome** | Boolean | Default is `False`. Defines if exomes samples are used. |

        
#### Estimation of the Optimum Solution Example
```python 
from SigProfilerExtractor import estimate_best_solution as ebs
ebs.estimate_solution(base_csvfile="All_solutions_stat.csv", 
          All_solution="All_Solutions", 
          genomes="Samples.txt", 
          output="results", 
          title="Selection_Plot",
          stability=0.8, 
          min_stability=0.2, 
          combined_stability=1.0,
          allow_stability_drop=False,
          exome=False)
```                

#### Estimation of the Optimum Solution Output
The files below will be generated in the output folder:
| File Name | Description |
| ----- | ----- |
| **All_solutions_stat.csv** | A csv file that contains the statistics of all solutions. |
| **selection_plot.pdf** | A plot that depict the Stability and Mean Sample Cosine Distance for different solutions. |

### <a name="decompose"></a> Decompose

For decomposition of de novo signatures please use [SigProfilerAssignment](https://github.com/SigProfilerSuite/SigProfilerAssignment)
        
### <a name="plotActivity"></a> Activity Stacked Bar Plot
Generates a stacked bar plot showing activities in individuals

```python 
plotActivity(activity_file, output_file = "Activity_in_samples.pdf", bin_size = 50, log = False)
``` 

| Parameter | Variable Type | Parameter Description |
| --------------------- | -------- |-------- |
| **activity_file** | String | The standard output activity file showing the number of, or percentage of mutations attributed to each sample. The row names should be samples while the column names should be signatures. |
| **output_file** | String | The path and full name of the output pdf file, including ".pdf" |
| **bin_size** | Integer | Number of samples plotted per page, recommended: 50 |
        
#### Activity Stacked Bar Plot Example
```bash 
$ python plotActivity.py 50 sig_attribution_sample.txt test_out.pdf
``` 

## <a name="video_tutorials"></a> Video Tutorials
Take a look at our video tutorials for step-by-step instructions on how to install and run SigProfilerExtractor on Amazon Web Services.

### Tutorial #1: Installing SigProfilerExtractor on Amazon Web Services ###

[![Video Tutorial #3](https://img.youtube.com/vi/30JmjvJ-DtI/0.jpg)](https://www.youtube.com/watch?v=30JmjvJ-DtI/)

### Tutorial #2: Running the Quick Start Example Program ###

[![Video Tutorial #3](https://img.youtube.com/vi/BiBYZz_khIY/0.jpg)](https://www.youtube.com/watch?v=BiBYZz_khIY/)

### Tutorial #3: Reviewing the output from SigProfilerExtractor ###

[![Video Tutorial #3](https://img.youtube.com/vi/BchtNeaQlv0/0.jpg)](https://www.youtube.com/watch?v=BchtNeaQlv0/)

### GPU support

If CUDA out of memory exceptions occur, it will be necessary to reduce the number of CPU processes used (the `cpu` parameter).

#### For more information, help, and examples, please start at `docs/index.md`.

## <a name="citation"></a> Citation
Islam SMA, Díaz-Gay M, Wu Y, Barnes M, Vangara R, Bergstrom EN, He Y, Vella M, Wang J, Teague JW, Clapham P, Moody S, Senkin S, Li YR, Riva L, Zhang T, Gruber AJ, Steele CD, Otlu B, Khandekar A, Abbasi A, Humphreys L, Syulyukina N, Brady SW, Alexandrov BS, Pillay N, Zhang J, Adams DJ, Martincorena I, Wedge DC, Landi MT, Brennan P, Stratton MR, Rozen SG, and Alexandrov LB (2022) Uncovering novel mutational signatures by _de novo_ extraction with SigProfilerExtractor. __Cell Genomics__. doi: [10.1016/j.xgen.2022.100179](https://doi.org/10.1016/j.xgen.2022.100179).


## <a name="copyright"></a> Copyright
This software and its documentation are copyright 2018 as a part of the sigProfiler project. The SigProfilerExtractor framework is free software and is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

## <a name="contact"></a> Contact Information
Please address any queries or bug reports to Mark Barnes at mdbarnes@ucsd.edu
