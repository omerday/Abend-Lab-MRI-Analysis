# fMRI Analysis Pipeline for WAR Task (Threat Appraisal & Emotion Regulation)

This directory contains the modular, reproducible, and production-grade fMRI analysis pipeline for the **Threat Appraisal and Emotion Regulation (WAR)** task paradigm, conducted by the **Abend Lab for Neuroscience of Psychopathology**. Built around AFNI (`sswarper2`, `afni_proc.py`, `3dttest++`, `3dLMEr`, `@chauffeur_afni`), the pipeline provides automated end-to-end processing—from raw BIDS datasets and electrodermal skin conductance response (SCR) records to publication-ready statistical activation maps and QC PDF reports.

---

## Table of Contents
- [Paradigm Overview](#paradigm-overview)
  - [Experimental Design](#experimental-design)
  - [28-Second Initial Lag Blocks](#28-second-initial-lag-blocks)
  - [11-Bin TR Expansion for Autonomic SCR](#11-bin-tr-expansion-for-autonomic-scr)
  - [Image-Level SCR Delta Amplitude Modulation](#image-level-scr-delta-amplitude-modulation)
- [Directory Structure](#directory-structure)
- [Prerequisites & Environment Setup](#prerequisites--environment-setup)
- [Configuration Reference](#configuration-reference)
  - [Main Configuration (`analysis_configs/main_config.toml`)](#main-configuration-analysis_configsmain_configtoml)
  - [Analysis Models (`analysis_configs/analysis_models.toml`)](#analysis-models-analysis_configsanalysis_modelstoml)
- [Environment Variables](#environment-variables)
- [AFNI Neuroimaging Parameters & Rationale](#afni-neuroimaging-parameters--rationale)
  - [Repetition Time (TR = 2.0s)](#repetition-time-tr--20s)
  - [Multi-Echo Echo Times & Optimal Combination (OC)](#multi-echo-echo-times--optimal-combination-oc)
  - [Non-Linear Anatomical Registration (`sswarper2` & Cost Function `lpa`)](#non-linear-anatomical-registration-sswarper2--cost-function-lpa)
  - [Spatial Smoothing (4.0 mm FWHM)](#spatial-smoothing-40-mm-fwhm)
  - [Motion Censoring (0.5 mm Euclidean Norm)](#motion-censoring-05-mm-euclidean-norm)
  - [Outlier Censoring (5% Outlier Fraction)](#outlier-censoring-5-outlier-fraction)
  - [Intermediate Functional Brick Cleanup (`KEEP_PB00_PB04`)](#intermediate-functional-brick-cleanup-keep_pb00_pb04)
- [Workflow & Step Organization](#workflow--step-organization)
  - [First-Level Analysis (`run_analysis.py`)](#first-level-analysis-run_analysispy)
  - [Group-Level Analysis (`run_analysis.py --step group_analysis`)](#group-level-analysis-run_analysispy---step-group_analysis)
- [Statistical Modeling Architecture](#statistical-modeling-architecture)
  - [First-Level Models (`by_block`, `by_image`, `by_scr_bins`)](#first-level-models-by_block-by_image-by_scr_bins)
  - [Group Linear Mixed Effects (`3dLMEr` with 3dClustSim ACF)](#group-linear-mixed-effects-3dlmer-with-3dclustsim-acf)
  - [Group T-Tests (`3dttest++`)](#group-t-tests-3dttest)
- [CLI Usage Guide](#cli-usage-guide)
  - [Main Controller (`run_analysis.py`)](#main-controller-run_analysispy-1)
  - [Results & QC Exporter (`export_results.py`)](#results--qc-exporter-export_resultspy)
  - [Multi-Subject Report Merger (`concatenate_reports.py`)](#multi-subject-report-merger-concatenate_reportspy)
  - [TR Magnitude Generator (`utils/create_tr_magnitude_file.py`)](#tr-magnitude-generator-utilscreate_tr_magnitude_filepy)
  - [Ledalab ERA Processor (`utils/process_era_files.py`)](#ledalab-era-processor-utilsprocess_era_filespy)
  - [DICOM to BIDS Converter (`utils/mri_file_preprocess.py`)](#dicom-to-bids-converter-utilsmri_file_preprocesspy)
- [Output Directory Structure](#output-directory-structure)
- [Quality Control & Verification](#quality-control--verification)

---

## Paradigm Overview

### Experimental Design
The **WAR** experiment investigates neural and autonomic reactivity during threat appraisal, emotional provocation, and cognitive regulation in healthy and clinical cohorts (e.g., MDMA vs. Control groups).

Participants complete two functional MRI runs per session. Each run features:
- **Emotional Blocks (22-second duration)**:
  - **Negative Blocks** (Event code `31`): Series of threatening, high-arousal scenes.
  - **Neutral Blocks** (Event code `51`): Series of everyday, low-arousal scenes.
  - **Positive Blocks** (Event code `71`): Series of pleasant, rewarding scenes.
- **Image Events (4-second duration)**:
  - Negative images: Codes `31`, `32`, `33`, `34`.
  - Neutral images: Codes `51`, `52`, `53`, `54`.
  - Positive images: Codes `71`, `72`, `73`, `74`.
- **Rest / Inter-Block Baseline (variable duration)**:
  - Event codes `22` and `24`.

---

### 28-Second Initial Lag Blocks
In the WAR paradigm, functional scan acquisition begins with an initial 28-second stabilization and baseline period prior to task onset.
- **Mathematical Handling in `create_tr_magnitude_file.py`**:
  When aligning external psychophysiological regressors (such as Skin Conductance Response [SCR]) with functional volumes:
  - For `lag = 28`, the initial 28 seconds (corresponding to 14 TRs at $\text{TR} = 2.0$ s) are subtracted from event timestamps ($t' = t - 28$). Events occurring before $t'=0$ are discarded.
  - The resulting output vector length is exactly **286 TRs** ($300 - 14 = 286$).
  - For `lag = 0` (or sessions without initial lead-in), the scan duration is modeled as the full **300 TRs**.
- **TR Bin Slotting Formula**:
  $$\text{index} = \text{int}\left(\frac{\text{Time} - \text{lag}}{2.0}\right)$$

---

### 11-Bin TR Expansion for Autonomic SCR
Autonomic skin conductance responses unfold over 15–25 seconds following sympathetic nervous system activation. In `war_analysis/utils/process_era_files.py` (`process_binned_era`):
- Each emotional block start event (Codes `31`, `51`, `71`) expands into **11 consecutive TR bins** spaced by 2.0 seconds:
  $$t_j = t + (j \times 2.0) \quad \text{for } j \in \{0, 1, 2, \dots, 10\}$$
- This covers the entire 22-second block duration ($11 \times 2.0 = 22.0$ s), enabling high-resolution modeling of continuous autonomic arousal trajectories without assuming a canonical hemodynamic response shape.

---

### Image-Level SCR Delta Amplitude Modulation
In `war_analysis/utils/process_era_files.py` (`process_image_era`):
- Ledalab Continuous Decomposition Analysis (CDA) separates tonic electrodermal level (`CDA.Tonic`) from phasic stimulus-locked response (`Global.Mean`).
- Baseline-corrected phasic amplitude is computed and rounded to 5 decimal places:
  $$\text{Amplitude} = \text{round}(\text{Global.Mean} - \text{CDA.Tonic}, 5)$$
- Negative delta amplitudes (where tonic decay exceeds phasic deflection) are strictly preserved with exact algebraic sign.

---

## Directory Structure

```text
war_analysis/
├── analysis_configs/               # Declarative TOML configuration files
│   ├── main_config.toml            # Global paths, subject rosters, per-session lags, and AFNI parameters
│   └── analysis_models.toml        # First-level GLM regressor definitions & group-level models
├── scripts/                        # Modular ShellCheck-compliant AFNI execution scripts
│   ├── 00_create_timings.sh        # Converts BIDS event TSVs and ERA files into AFNI .1D files
│   ├── 01_preprocess_anat.sh       # Runs sswarper2 non-linear skull-stripping & MNI normalization
│   ├── 02_preprocess_func.sh       # Runs afni_proc.py multi-echo functional preprocessing
│   ├── 03_run_glm.sh               # Runs first-level GLM regression and @chauffeur_afni QC rendering
│   ├── 04_run_group_analysis.sh    # Executes 3dLMEr (3dClustSim ACF) or 3dttest++ group models
│   └── utils_colors.sh             # ANSI color logging utility
├── utils/                          # Specialized data preparation & format conversion utilities
│   ├── create_tr_magnitude_file.py # Maps binned SCR events into TR magnitude vectors
│   ├── process_era_files.py        # Ledalab ERA parser with 11-bin block expansion
│   ├── mri_file_preprocess.py      # Raw Siemens DICOM to BIDS NIfTI converter
│   ├── convert_qc_to_pdf.py        # Converts APQC HTML reports to PDF
│   └── rename_subjects.py          # BIDS subject naming and folder normalization utility
├── run_analysis.py                 # Multi-core Python CLI controller for all first-level & group jobs
├── export_results.py               # Generates consolidated QC & GLM activation PDFs
├── concatenate_reports.py          # Merges single-subject PDF reports into multi-subject binders
└── README.md                       # Comprehensive pipeline documentation
```

> **Note on Group Analysis Architecture**: All first-level processing steps AND all group-level statistical models (`3dLMEr`, `3dttest++`) are executed through the unified controller `run_analysis.py` (via `--step group_analysis`). (The legacy standalone runner `run_group_level.py` has been consolidated directly into `run_analysis.py`).

---

## Prerequisites & Environment Setup

1. **AFNI (Analysis of Functional NeuroImages)**:
   - Must be installed and available on `PATH`.
   - Core tools: `sswarper2`, `afni_proc.py`, `3dDeconvolve`, `3dREMLfit`, `3dLMEr`, `3dttest++`, `3dFWHMx`, `3dClustSim`, `timing_tool.py`, `@chauffeur_afni`.
   - Requires R with `lme4`, `afex`, and `phia` packages for `3dLMEr`.
2. **Python 3.8+**:
   - Uses standard library `unittest` for the automated test suite.
   - Install additional packages:
     ```bash
     pip install toml pandas numpy rich fpdf
     ```
3. **Template Datasets**:
   - `MNI152_2009_template_SSW.nii.gz` (anatomical non-linear warping)
   - `MNI152_2009_template.nii.gz` (functional spatial normalization & visual underlay)

---

## Configuration Reference

### Main Configuration (`analysis_configs/main_config.toml`)

`main_config.toml` manages global paths, subjects, per-session lag parameters, and AFNI thresholds:

```toml
# Raw BIDS data directory (or GCS URI: gs://abend-lab-mri-analysis/inputs/war)
input_dir = "/home/user/Documents/WAR/Data/Input"

# Output derivatives directory (or GCS URI: gs://abend-lab-mri-analysis/outputs/war)
output_dir = "/media/user/VERBATIM SD/WAR/Output"

# Local scratch directory for fast I/O during execution
scratch_dir = "/tmp/afni_scratch"

# Automatically delete local scratch files once synced to output_dir
cleanup_scratch = true

# Keep intermediate pb00-pb04 functional preprocessing bricks (default: false)
keep_pb00_pb04 = false

# Default AFNI Preprocessing & GLM Parameters
blur_size = 4.0
tr = 2.0
censor_motion_threshold = 0.5
censor_outlier_threshold = 0.05

# Subjects with cohort groupings and session-specific lag parameters
[[subjects]]
id = "sub-AL01"
group = "MDMA"
sessions = [
  { id = 1, lag_block_1 = 10, lag_block_2 = 12 },
  { id = 2, lag_block_1 = 9,  lag_block_2 = 11 }
]

[[subjects]]
id = "sub-AL02"
group = "Control"
sessions = [
  { id = 1, lag_block_1 = 8, lag_block_2 = 8 }
]
```

### Analysis Models (`analysis_configs/analysis_models.toml`)

Defines first-level GLM variations and group analyses:

```toml
# 1. Emotional Block Model
[by_block]
description = "GLM analysis by emotional block (Negative, Positive, Neutral)."
stim_files = [
    "timings/negative_block.1D",
    "timings/positive_block.1D",
    "timings/neutral_block.1D",
    "timings/rest.1D"
]
stim_labels = ["neg_blck", "pos_blck", "neut_blck", "rest"]
basis = "BLOCK(22,1)"
glt = [
    { sym = "neg_blck - neut_blck", label = "neg-neut_blck" },
    { sym = "neg_blck - rest", label = "neg_blck-rest" },
    { sym = "pos_blck - neut_blck", label = "pos-neut_blck" },
    { sym = "neg_blck - pos_blck", label = "neg-pos_blck" }
]

# Group-Level 3dLMEr Linear Mixed Effects
[[by_block.group_analyses]]
name = "mdma_vs_control_s1"
type = "3dLMEr"
model = "group*stimulus+(1|Subj)"
description = "Compare MDMA vs Control groups in session 1."
groups = ["MDMA", "Control"]
sessions = [1]
data_table_rows = [
    { stimulus = "neg",  contrast = "neg_blck#0_Coef" },
    { stimulus = "pos",  contrast = "pos_blck#0_Coef" },
    { stimulus = "neut", contrast = "neut_blck#0_Coef" }
]
glt = [
    { sym = "group : 1*MDMA -1*Control stimulus : 1*neg", label = "neg_mdma_gt_control" }
]

# Group-Level 3dttest++ One-Sample T-Test
[[by_block.group_analyses]]
name = "mdma_s1_neg_vs_neut"
type = "3dttest++"
description = "One-sample t-test for MDMA group in session 1 on neg-neut contrast."
groups = ["MDMA"]
sessions = [1]
contrast = "neg-neut_blck#0_Coef"
setA_label = "MDMA_S1_NegVsNeut"
```

---

## Environment Variables

| Environment Variable | Overrides | Description |
| :--- | :--- | :--- |
| `MRI_INPUT_DIR` | `input_dir` | Dynamically points to raw BIDS input data (local path or `gs://...`). |
| `MRI_OUTPUT_DIR` | `output_dir` | Specifies derivatives destination (local path or `gs://...`). |
| `MRI_REPORTS_DIR` | Destination root | Specifies destination for exported QC PDFs in `export_results.py`. |
| `KEEP_PB00_PB04` | `keep_pb00_pb04` | Set to `"1"` to retain intermediate functional preprocessing bricks (`pb00`–`pb04`). Defaults to `"0"`. |

---

## AFNI Neuroimaging Parameters & Rationale

### Repetition Time (TR = 2.0s)
- **Value**: `tr = 2.0` (seconds).
- **Physical Rationale**: Defines functional sampling interval ($f_{\text{Nyq}} = 0.25$ Hz). Accommodates multi-slice multi-echo EPI readouts while precisely binning behavioral image events (4 s duration = 2 TRs) and block events (22 s duration = 11 TRs).

### Multi-Echo Echo Times & Optimal Combination (OC)
- **Values**: `-echo_times 13.6 25.96 38.3` (ms) with `-combine_method OC`.
- **Physical Rationale**:
  In threat appraisal paradigms, primary regions of interest include the **amygdala**, **ventromedial prefrontal cortex (vmPFC)**, and **anterior insula**. These regions border air-tissue interfaces (nasopharyngeal cavity, sphenoid sinuses) and suffer severe susceptibility-induced gradient dropout at conventional single-echo readouts (TE ~30 ms).
  - Short echo (13.6 ms) retains strong signal in dropout-prone vmPFC and amygdala.
  - Middle and long echoes (25.96 ms, 38.3 ms) maximize BOLD sensitivity in dorsal cortical areas.
  - **Optimal Combination (`OC`)** weights each voxel according to its estimated $T_2^*$ decay rate:
    $$w(TE_m) = \frac{TE_m \cdot \exp(-TE_m / T_2^*)}{\sum_{j=1}^3 TE_j \cdot \exp(-TE_j / T_2^*)}$$
    This recovers signal in ventral affective circuits while suppressing scanner drift.

### Non-Linear Anatomical Registration (`sswarper2` & Cost Function `lpa`)
- **Parameters**: `sswarper2 -giant_move -cost_nl_final lpa -minp 8`.
- **Rationale**:
  - High-precision anatomical normalization to `MNI152_2009_template_SSW.nii.gz`.
  - **Local Pearson Correlation (`lpa`)**: Computes local Pearson correlation across moving spherical patches, preventing global contrast distortions from corrupting subcortical alignment (amygdalar and hippocampal subnuclei).
  - `-giant_move`: Resolves large initial positional or angular offsets between native head position and MNI coordinates.
  - `-minp 8`: Enforces 8 mm patch sizes for numerical stability.

### Spatial Smoothing (4.0 mm FWHM)
- **Parameter**: `-blur_size 4` (mm FWHM isotropic Gaussian kernel).
- **Rationale**:
  Affective neuroimaging requires anatomical precision: the basolateral vs. central amygdala and bed nucleus of the stria terminalis (BNST) are small structures spanning only several millimeters. An aggressive smoothing kernel (e.g., 6–8 mm) causes signal blending with adjacent parahippocampal gyrus and CSF ventricles. A conservative 4.0 mm blur preserves spatial specificity while improving SNR.

### Motion Censoring (0.5 mm Euclidean Norm)
- **Parameter**: `-regress_censor_motion 0.5`.
- **Formulation**:
  $$\text{enorm}_t = \sqrt{(\Delta \text{roll}_t)^2 + (\Delta \text{pitch}_t)^2 + (\Delta \text{yaw}_t)^2 + (\Delta dS_t)^2 + (\Delta dL_t)^2 + (\Delta dP_t)^2}$$
- Volumes exceeding $\text{enorm}_t > 0.5$ mm are excluded from GLM regression, preventing motion-induced spurious correlations in affective contrast estimates.

### Outlier Censoring (5% Outlier Fraction)
- **Parameter**: `-regress_censor_outliers 0.05`.
- TRs where $> 5\%$ of automasked voxels exhibit severe signal deviations (flagged by `3dToutcount`) are scrubbed from GLM estimation.

### Intermediate Functional Brick Cleanup (`KEEP_PB00_PB04`)
- Intermediate functional processing bricks (`pb00` through `pb04`) and temporary `rm.*` files are automatically deleted upon completion when `KEEP_PB00_PB04=0`.
- The final scaled brick (`pb05.scale`), motion regressors, censor vectors, `fitts`, `errts`, and `stats.*` datasets are **strictly preserved**, saving 15–20 GB per subject.

---

## Workflow & Step Organization

### First-Level Analysis (`run_analysis.py`)
Executes first-level processing for individual subjects:
1. `create_timings` (`00_create_timings.sh`): Generates AFNI `.1D` timing files from event TSVs and ERA files.
2. `preprocess_anat` (`01_preprocess_anat.sh`): Runs `sswarper2` skull-stripping and non-linear MNI warping.
3. `preprocess_func` (`02_preprocess_func.sh`): Runs multi-echo `afni_proc.py` functional preprocessing.
4. `glm` (`03_run_glm.sh`): Runs first-level GLM regression for specified models.
5. `preprocess`: Composite step running `create_timings` $\rightarrow$ `preprocess_anat` $\rightarrow$ `preprocess_func`.
6. `all`: Composite step running `preprocess` $\rightarrow$ `glm`.

### Group-Level Analysis (`run_analysis.py --step group_analysis`)
Executes group-level statistical models using `--step group_analysis --analysis <model> --group_model <name>`:
- Automatically filters eligible subjects by group and session.
- Validates availability of first-level contrast sub-bricks.
- Dynamically compiles `data_table.txt` for `3dLMEr` or compiles input dataset arrays for `3dttest++`.
- Computes spatial autocorrelation function (ACF) residual smoothness via `3dFWHMx -acf` and attaches `3dClustSim` cluster extent tables.
- Renders automated publication montage images via `@chauffeur_afni`.

---

## Statistical Modeling Architecture

### First-Level Models
- **`by_block`**:
  - Stimulus files: `negative_block.1D`, `positive_block.1D`, `neutral_block.1D`, `rest.1D`.
  - Basis: `BLOCK(22,1)` (22-second block duration, 1-second onset delay).
  - Contrasts: `neg-neut_blck`, `neg_blck-rest`, `pos-neut_blck`, `neg-pos_blck`.
- **`by_image`**:
  - Stimulus files: `negative_image.1D`, `positive_image.1D`, `neutral_image.1D`, `rest.1D`.
  - Basis: `BLOCK(4,1)` (4-second image presentation).
  - Contrasts: `neg-neut_image`, `pos-neut_image`, `neg-pos_image`.
- **`by_scr_bins`**:
  - Stimulus files: `timings/scr_binned.1D`.
  - Basis: `GAM` with `stim_types = "file"` (external TR magnitude regressor).

---

### Group Linear Mixed Effects (`3dLMEr` with 3dClustSim ACF)
For complex multi-group, multi-session designs with repeated measures or missing sessions:
- **AFNI Command**: `3dLMEr -prefix <prefix> -mask <mask> -SS_type 3 -model "group*stimulus+(1|Subj)" -dataTable @data_table.txt -resid <resid>`
- **Cluster Extent Thresholding**:
  1. Residuals (`<prefix>_resid+tlrc`) are evaluated with `3dFWHMx -mask <mask> -acf NULL`.
  2. Non-Gaussian ACF parameters ($a, b, c$) are passed to `3dClustSim`:
     ```bash
     3dClustSim -mask <mask> -acf a b c -both -prefix <prefix>_ClustSim
     ```
  3. Generated cluster-size tables are permanently attached to the group dataset headers via the generated `.cmd` script.

---

### Group T-Tests (`3dttest++`)
For simple one-sample or two-sample group comparisons:
- **AFNI Command**: `3dttest++ -prefix <prefix> -mask <mask> -setA <label> <files...>`
- **WAR Invariance Note**: In accordance with the WAR pipeline design, `04_run_group_analysis.sh` omits `-clustsim` on `3dttest++`, enabling custom downstream thresholding or permutation simulations.

---

## CLI Usage Guide

### Main Controller (`run_analysis.py`)

```text
usage: run_analysis.py [-h] [--step {create_timings,preprocess_anat,preprocess_func,glm,preprocess,all,group_analysis} ...]
                       [--subject SUBJECT [SUBJECT ...]] [--analysis ANALYSIS [ANALYSIS ...]]
                       [--group_model GROUP_MODEL] [--session SESSION] [--n_procs N_PROCS]
                       [--scratch_dir SCRATCH_DIR] [--clean_scratch] [--no_scratch]
                       [--input_dir INPUT_DIR] [--output_dir OUTPUT_DIR] [--keep_pb00_pb04]
```

#### CLI Examples:

```bash
# 1. Run all preprocessing for a single subject
python war_analysis/run_analysis.py --subject sub-AL01 --step preprocess

# 2. Run first-level GLM for the by_block model across 4 cores
python war_analysis/run_analysis.py --step glm --analysis by_block --n_procs 4

# 3. Run complete first-level pipeline for multiple subjects
python war_analysis/run_analysis.py --subject sub-AL01 sub-AL02 sub-AL03 --step all --n_procs 3

# 4. Run group analysis (3dLMEr) comparing MDMA vs Control
python war_analysis/run_analysis.py \
    --step group_analysis \
    --analysis by_block \
    --group_model mdma_vs_control_s1

# 5. Run group analysis (3dttest++) one-sample t-test
python war_analysis/run_analysis.py \
    --step group_analysis \
    --analysis by_block \
    --group_model mdma_s1_neg_vs_neut
```

---

### Results & QC Exporter (`export_results.py`)

Exports preprocessed APQC HTML reports and first-level GLM activation maps to consolidated PDF documents:

```bash
python war_analysis/export_results.py --subject sub-AL01 --output_dir "/media/user/VERBATIM SD/WAR/Output"
```

---

### Multi-Subject Report Merger (`concatenate_reports.py`)

Merges individual PDF reports into a unified project-level QC binder:

```bash
python war_analysis/concatenate_reports.py \
    --reports_dir "/media/user/VERBATIM SD/WAR/Output/reports" \
    --output "war_consolidated_qc_report.pdf"
```

---

### TR Magnitude Generator (`utils/create_tr_magnitude_file.py`)

Converts binned TSV events into a single-column 1D TR magnitude file:

```bash
python war_analysis/utils/create_tr_magnitude_file.py \
    --binned_tsv "binned_scr_run-1.txt" \
    --lag 28 \
    --output "timings/scr_binned_run-1.1D"
```

---

### Ledalab ERA Processor (`utils/process_era_files.py`)

Processes Ledalab Event-Related Analysis (ERA) exports into image-level and 11-bin block expansion timing files:

```bash
python war_analysis/utils/process_era_files.py \
    --era_path "/path/to/sub-AL01_era.txt" \
    --events_path "/path/to/sub-AL01/ses-1/func" \
    --output_path "/path/to/sub-AL01/ses-1/func/timings" \
    --blocks 2
```

---

### DICOM to BIDS Converter (`utils/mri_file_preprocess.py`)

Converts raw Siemens console DICOM series into BIDS-compliant NIfTI layout:

```bash
python war_analysis/utils/mri_file_preprocess.py \
    --dicom_dir "/path/to/raw_dicoms" \
    --bids_dir "/path/to/BIDS_input" \
    --subject "sub-AL01" \
    --session 1
```

---

## Output Directory Structure

```text
/output_dir/
├── sub-AL01/
│   ├── ses-1/
│   │   ├── anat_warped/                      # Output from 01_preprocess_anat.sh
│   │   │   ├── anatSS.sub-AL01.nii           # Skull-stripped anatomical in native space
│   │   │   ├── anatQQ.sub-AL01.nii           # Non-linearly warped anatomical in MNI space
│   │   │   ├── anatQQ.sub-AL01.aff12.1D      # Affine alignment matrix
│   │   │   └── anatQQ.sub-AL01_WARP.nii      # Displacement warp field
│   │   ├── func_preproc/                     # Output from 02_preprocess_func.sh
│   │   │   └── sub-AL01_preproc.results/
│   │   │       ├── pb05.sub-AL01_preproc.r01.scale+tlrc.HEAD # Scaled functional timeseries
│   │   │       ├── dfile_rall.1D             # Motion parameters
│   │   │       ├── censor_sub-AL01_combined_2.1D # Motion and outlier censor vector
│   │   │       ├── mask_epi_anat.sub-AL01+tlrc.HEAD # Intersection EPI-anatomical mask
│   │   │       └── QC_sub-AL01/              # APQC HTML quality review
│   │   └── glm/                              # Output from 03_run_glm.sh
│   │       ├── by_block/
│   │       │   ├── stats.sub-AL01_by_block+tlrc.HEAD # Statistical contrast bricks
│   │       │   ├── fitts.sub-AL01_by_block+tlrc.HEAD # Full model fit
│   │       │   ├── errts.sub-AL01_by_block+tlrc.HEAD # Residual timeseries
│   │       │   └── QC/                       # @chauffeur_afni 3x3 axial montage PNGs
│   │       └── by_image/
│   │           └── ...
│   └── ses-2/
│       └── ...
└── group_analysis/                           # Output from 04_run_group_analysis.sh
    └── by_block/
        ├── mdma_vs_control_s1/
        │   ├── result_mdma_vs_control_s1+tlrc.HEAD # 3dLMEr statistics
        │   ├── result_mdma_vs_control_s1_resid+tlrc.HEAD # Residuals for ACF
        │   ├── group_mask+tlrc.HEAD          # Overlap group mask
        │   ├── data_table.txt                # 3dLMEr input data table
        │   └── result_mdma_vs_control_s1_images/ # @chauffeur_afni group figures
        └── mdma_s1_neg_vs_neut/
            ├── result_mdma_s1_neg_vs_neut+tlrc.HEAD # 3dttest++ statistics
            └── ...
```

---

## Quality Control & Verification

1. **Automated Regression Suite**:
   ```bash
   python3 -m unittest discover -s tests -v
   ```
   Ensures 100% command invariance for `sswarper2`, `afni_proc.py`, `3dttest++`, `3dLMEr`, and exact mathematical equivalence for SCR timing generation.
2. **APQC HTML Verification**: Preprocessing review pages are generated automatically in `func_preproc/sub-XXX_preproc.results/QC_sub-XXX/index.html`.
3. **Chauffeur Axial Montages**: Rendered with clusterization (`-NN 2 -clust_nvox 35`) and bilateral $p < 0.05$ thresholding for immediate visual artifact detection.