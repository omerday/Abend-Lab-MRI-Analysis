# fMRI Analysis Pipeline for TIM Task (Thermal Pain & Anticipation)

This directory contains the modular, reproducible, and production-grade fMRI analysis pipeline for the **Thermal Pain and Anticipation (TIM)** task paradigm, conducted by the **Abend Lab for Neuroscience of Psychopathology**. Built primarily around AFNI (`sswarper2`, `afni_proc.py`, `3dttest++`, `3dLMEr`, `@chauffeur_afni`), the pipeline provides automated end-to-end processing—from raw BIDS datasets and electrodermal skin conductance response (SCR) records to publication-ready statistical activation maps and QC PDF reports.

---

## Table of Contents
- [Paradigm Overview](#paradigm-overview)
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
- [CLI Usage Guide](#cli-usage-guide)
  - [Main Controller (`run_analysis.py`)](#main-controller-run_analysispy)
  - [Results & QC Exporter (`export_results.py`)](#results--qc-exporter-export_resultspy)
  - [Multi-Subject Report Merger (`concatenate_reports.py`)](#multi-subject-report-merger-concatenate_reportspy)
  - [HTML to PDF Converter (`convert_qc_to_pdf.py`)](#html-to-pdf-converter-convert_qc_to_pdfpy)
  - [Ledalab ERA Timing Converter (`era_to_timing.py`)](#ledalab-era-timing-converter-era_to_timingpy)
  - [DICOM to BIDS Converter (`mri_file_preprocess.py`)](#dicom-to-bids-converter-mri_file_preprocesspy)
- [Output Directory Structure](#output-directory-structure)
- [Quality Control & Verification](#quality-control--verification)

---

## Paradigm Overview

The **TIM** (Thermal Anticipation and Pain) experiment investigates neural mechanisms underlying acute pain processing, anticipatory threat appraisal, and psychophysiological arousal.

Participants undergo 5 functional imaging runs. Each run presents:
1. **Visual Anticipation Cues (Squares)**: Color-coded visual cues predicting impending thermal heat levels:
   - Green square (Event Code `21`): Predicts low-temperature stimulation (Multiplier $\times 2$).
   - Yellow square (Event Code `41`): Predicts medium-temperature stimulation (Multiplier $\times 6$).
   - Red square (Event Code `81`): Predicts high-temperature stimulation (Multiplier $\times 8$).
2. **Pre-Heat Baseline Window**: A brief anticipation window immediately prior to thermal ramp (Codes `25`, `45`, `85`).
3. **Thermal Pain Delivery**: Contact heat delivered to the volar forearm via an MRI-compatible thermal stimulator (Codes `26`, `46`, `86`).
4. **Subjective Pain Rating**: Continuous visual analogue scale (VAS) rating of experienced pain intensity (Codes `27`, `47`, `87`).
5. **Autonomic Electrodermal Response (SCR)**: Continuous skin conductance data recorded via Biopac and analyzed using Ledalab Event-Related Analysis (ERA) to extract tonic and phasic amplitude modulations.

---

## Directory Structure

```text
tim_analysis/
├── analysis_configs/               # Declarative TOML configuration files
│   ├── main_config.toml            # Global paths, subject rosters, sessions, and default parameters
│   └── analysis_models.toml        # First-level GLM regressor definitions & group-level models
├── scripts/                        # Modular ShellCheck-compliant AFNI execution scripts
│   ├── 00_create_timings.sh        # Converts BIDS event TSVs and Ledalab ERAs into AFNI .1D files
│   ├── 01_preprocess_anat.sh       # Runs sswarper2 non-linear skull-stripping & MNI normalization
│   ├── 02_preprocess_func.sh       # Runs afni_proc.py multi-echo functional preprocessing
│   ├── 03_run_glm.sh               # Runs first-level GLM regression and @chauffeur_afni QC rendering
│   ├── 04_run_group_analysis.sh    # Executes 3dttest++ (-clustsim) or 3dLMEr (3dClustSim ACF)
│   └── utils_colors.sh             # ANSI color logging utility
├── run_analysis.py                 # Multi-core Python CLI controller for first-level and group jobs
├── export_results.py               # Generates consolidated QC & GLM activation PDFs
├── concatenate_reports.py          # Merges single-subject PDF reports into multi-subject binders
├── convert_qc_to_pdf.py            # Converts afni_proc.py APQC HTML reports to PDF
├── era_to_timing.py                # Extracts Ledalab ERA SCR metrics and pairs them with event onsets
├── mri_file_preprocess.py          # Converts raw Siemens DICOMs to BIDS-compliant NIfTI layout
├── requirements.txt                # Optional Python dependencies (rich, toml, fpdf, pdfkit)
└── README.md                       # Comprehensive pipeline documentation
```

---

## Prerequisites & Environment Setup

1. **AFNI (Analysis of Functional NeuroImages)**:
   - Must be installed and present on `PATH`.
   - Required binaries: `sswarper2`, `afni_proc.py`, `3dDeconvolve`, `3dREMLfit`, `3dttest++`, `3dLMEr`, `3dFWHMx`, `3dClustSim`, `timing_tool.py`, `@chauffeur_afni`, `3dinfo`, `3dcalc`.
   - Requires R packages for `3dLMEr`: `lme4`, `afex`, `phia`.
2. **Python 3.8+**:
   - Uses Python standard library for core CLI execution and unittest suites.
   - Install optional formatting and reporting libraries:
     ```bash
     pip install -r requirements.txt
     ```
3. **Template Datasets**:
   - `MNI152_2009_template_SSW.nii.gz` (for `sswarper2` anatomical warping)
   - `MNI152_2009_template.nii.gz` (for `afni_proc.py` and `@chauffeur_afni` underlay)
   - Typically installed in `/opt/afni_templates/` or located in the project root.

---

## Configuration Reference

### Main Configuration (`analysis_configs/main_config.toml`)

`main_config.toml` manages global paths, subjects, sessions, and default AFNI parameters:

```toml
# Raw BIDS data directory (or GCS URI: gs://abend-lab-mri-analysis/inputs/tim)
input_dir = "/home/user/Documents/TIM/Pilot/Input"

# Output derivatives directory (or GCS URI: gs://abend-lab-mri-analysis/outputs/tim)
output_dir = "/media/user/VERBATIM SD/TIM/Output"

# Local scratch directory for fast I/O during execution
scratch_dir = "/tmp/afni_scratch"

# Automatically delete local scratch files once synced to output_dir
cleanup_scratch = true

# Keep intermediate pb00-pb04 functional preprocessing bricks (default: false to save 15+ GB/subject)
keep_pb00_pb04 = false

# Default AFNI Preprocessing & GLM Parameters
blur_size = 4.0
tr = 2.0
censor_motion_threshold = 0.5
censor_outlier_threshold = 0.05

# Subject roster with session metadata
[[subjects]]
id = "sub-435"
group = "TIM"
sessions = [
  { id = 1, has_scr = true }
]
```

### Analysis Models (`analysis_configs/analysis_models.toml`)

Defines first-level GLM regressors, basis functions, contrast vectors, and group models:

```toml
[pain_by_rating]
description = "Pain period amplitude modulated by subjective pain rating."
stim_files = ["timings/pain_rating_amp.1D"]
stim_labels = ["PAIN"]
basis = "BLOCK(4,1)"
stim_types = "AM2"
requires_scr = false
glt = []

[[pain_by_rating.group_analyses]]
name = "pain_by_rating"
type = "3dttest++"
description = "One-sample t-test for pain modulated by rating."
groups = ["TIM"]
sessions = [1]
contrast = "PAIN#1_Coef"
setA_label = "PAIN"
```

---

## Environment Variables

All filesystem paths and cleanup policies can be dynamically overridden at runtime using environment variables:

| Environment Variable | Overrides | Description |
| :--- | :--- | :--- |
| `MRI_INPUT_DIR` | `input_dir` | Points `run_analysis.py` to local BIDS raw data or GCS bucket (`gs://...`). |
| `MRI_OUTPUT_DIR` | `output_dir` | Specifies the destination directory for preprocessed derivatives and GLMs. |
| `MRI_REPORTS_DIR` | Destination root | Specifies destination for exported QC PDFs in `export_results.py`. |
| `KEEP_PB00_PB04` | `keep_pb00_pb04` | If set to `"1"`, disables automatic deletion of intermediate functional bricks (`pb00` through `pb04`). Defaults to `"0"`. |

---

## AFNI Neuroimaging Parameters & Rationale

Every AFNI processing choice in the TIM pipeline is grounded in empirical fMRI physics and neuroimaging methodology:

### Repetition Time (TR = 2.0s)
- **Parameter**: `tr = 2.0` (seconds).
- **Physical Rationale**: Defines the temporal sampling rate ($\Delta t = 2.0$ s), corresponding to a Nyquist frequency of $f_{\text{Nyq}} = \frac{1}{2 \cdot \text{TR}} = 0.25$ Hz. This interval captures canonical BOLD hemodynamic response functions (peaking at ~5–6 s post-stimulus) while enabling whole-brain multi-slice multi-band coverage without excessive slice-timing dispersion.

### Multi-Echo Echo Times & Optimal Combination (OC)
- **Parameter**: `-echo_times 13.6 25.96 38.3` (ms) with `-combine_method OC`.
- **Physical Rationale**:
  BOLD signal contrast is driven by transverse relaxation rate changes ($\Delta R_2^* = 1 / T_2^*$). Different brain tissues exhibit differing baseline $T_2^*$ relaxation times:
  - Short $T_2^*$ regions (e.g., orbitofrontal cortex, amygdala, ventral temporal cortex near air-tissue interfaces subject to macroscopic susceptibility gradients).
  - Long $T_2^*$ regions (e.g., dorsal anterior cingulate cortex, primary somatosensory cortex S1, posterior insula).
- **Optimal Combination Formulation**:
  AFNI's `OC` method estimates voxel-wise $T_2^*$ from average signal intensities and calculates echo weights according to:
  $$w(TE_m) = \frac{TE_m \cdot \exp(-TE_m / T_2^*)}{\sum_{j=1}^3 TE_j \cdot \exp(-TE_j / T_2^*)}$$
  This weighting maximizes the Contrast-to-Noise Ratio (CNR) across the entire brain, recovers signal in dropout-prone pain-regulatory regions, and effectively suppresses thermal noise and non-BOLD scanner drift.

### Non-Linear Anatomical Registration (`sswarper2` & Cost Function `lpa`)
- **Parameter**: `sswarper2 -giant_move -cost_nl_final lpa -minp 8`.
- **Rationale**:
  - Dual-purpose skull-stripping and non-linear template warping avoids circular dependency between brain extraction and normalization.
  - Template: `MNI152_2009_template_SSW.nii.gz` (ICBM 2009c Nonlinear Asymmetric MNI space, 1 mm isotropic resolution).
  - **Cost Function (`-cost_nl_final lpa`)**: Local Pearson Correlation (absolute value). Unlike global mutual information, LPA calculates Pearson correlation within localized spherical neighborhoods across the volume. This provides superior resistance to $B_1$ transmit/receive field inhomogeneities and localized radiofrequency coil sensitivity variations.
  - `-giant_move`: Expands the 3D translation and rotation search grid, accommodating large subject head pitch/yaw differences relative to the MNI template.
  - `-minp 8`: Enforces an 8 mm minimum patch size for stable local correlation estimation.

### Spatial Smoothing (4.0 mm FWHM)
- **Parameter**: `-blur_size 4` (mm FWHM isotropic Gaussian kernel).
- **Rationale**:
  Thermal pain pathways involve distinct, spatially fine-grained structures: dorsal posterior insula (dpIns), anterior midcingulate cortex (aMCC), thalamic ventroposterior lateral/medial nuclei (VPL/VPM), and primary somatosensory cortex (S1/S2). A wide smoothing kernel (e.g., 8 mm) causes signal bleeding between adjacent white matter, CSF, and functionally distinct sub-regions. A conservative 4.0 mm FWHM kernel improves SNR and satisfies Gaussian Random Field theory assumptions while strictly preserving anatomical specificity.

### Motion Censoring (0.5 mm Euclidean Norm)
- **Parameter**: `-regress_censor_motion 0.5`.
- **Mathematical Formulation**:
  Head motion parameters from 6 degrees of freedom (roll, pitch, yaw, $\Delta S, \Delta L, \Delta P$) are converted into first differences ($\Delta$). The Euclidean norm (enorm) is computed at each time point $t$:
  $$\text{enorm}_t = \sqrt{(\Delta \text{roll}_t)^2 + (\Delta \text{pitch}_t)^2 + (\Delta \text{yaw}_t)^2 + (\Delta dS_t)^2 + (\Delta dL_t)^2 + (\Delta dP_t)^2}$$
- Any volume where $\text{enorm}_t > 0.5$ mm is completely scrubbed from GLM regression. This prevents false-positive activation driven by head jolts coincident with acute thermal stimulation.

### Outlier Censoring (5% Outlier Fraction)
- **Parameter**: `-regress_censor_outliers 0.05`.
- **Rationale**:
  Computed via AFNI's `3dToutcount`. For each voxel, a low-order polynomial trend is fitted; timepoints exhibiting severe median absolute deviations (MAD) are flagged. If $> 5\%$ ($0.05$) of whole-brain automasked voxels are flagged as outliers at time $t$, that entire TR is censored. This scrubs global artifactual spikes caused by deep breaths, swallowing during pain, or transient RF hardware noise.

### Intermediate Functional Brick Cleanup (`KEEP_PB00_PB04`)
- **Behavior**:
  During multi-echo preprocessing, `afni_proc.py` generates gigabytes of intermediate brick files per subject:
  - `pb00.tcat`: Time-shifted raw echoes
  - `pb01.tshift`: Slice-timing corrected bricks
  - `pb02.volreg`: Rigid-body motion registered volumes
  - `pb03.combine`: Echo-combined datasets
  - `pb04.blur`: Smoothed volumes
  - `pb05.scale`: Voxel-wise percent signal change scaled datasets
- When `KEEP_PB00_PB04=0` (the default), `02_preprocess_func.sh` purges `pb00` through `pb04` and temporary `rm.*` files.
- **Guarantee**: `pb05.scale` (input to GLM regression), motion regressors, censor files, `fitts` (model fit), `errts` (residuals), and `stats.*` are **strictly retained**. This saves 15–25 GB per subject without affecting downstream statistical analyses or reproducibility.

---

## CLI Usage Guide

### Main Controller (`run_analysis.py`)

The primary orchestrator supporting single-subject, batch parallel, and cloud execution.

```text
usage: run_analysis.py [-h] [--step {create_timings,preprocess_anat,preprocess_func,glm,preprocess,all,group_analysis} ...]
                       [--subject SUBJECT [SUBJECT ...]] [--analysis ANALYSIS [ANALYSIS ...]]
                       [--group_model GROUP_MODEL] [--session SESSION] [--n_procs N_PROCS]
                       [--scratch_dir SCRATCH_DIR] [--clean_scratch] [--no_scratch]
                       [--input_dir INPUT_DIR] [--output_dir OUTPUT_DIR] [--keep_pb00_pb04]
```

#### Step Expansion:
- `create_timings`: Runs `00_create_timings.sh`.
- `preprocess_anat`: Runs `01_preprocess_anat.sh` (`sswarper2`).
- `preprocess_func`: Runs `02_preprocess_func.sh` (`afni_proc.py`).
- `glm`: Runs `03_run_glm.sh` for specified model(s).
- `preprocess`: Composite step running `create_timings` $\rightarrow$ `preprocess_anat` $\rightarrow$ `preprocess_func`.
- `all`: Composite step running `preprocess` $\rightarrow$ `glm`.
- `group_analysis`: Runs `04_run_group_analysis.sh`.

#### Execution Examples:

```bash
# 1. Run full preprocessing for a single subject
python tim_analysis/run_analysis.py --subject sub-435 --step preprocess

# 2. Run GLM regression for a specific model across 4 CPU cores
python tim_analysis/run_analysis.py --step glm --analysis pain_by_rating --n_procs 4

# 3. Run complete first-level pipeline for multiple subjects in parallel
python tim_analysis/run_analysis.py --subject sub-435 sub-473 sub-489 --step all --n_procs 3

# 4. Run group-level analysis for pain_by_rating model
python tim_analysis/run_analysis.py --step group_analysis --analysis pain_by_rating --group_model pain_by_rating

# 5. Execute with custom GCS or external hard drive paths
python tim_analysis/run_analysis.py \
    --input_dir "/media/user/PortableSSD/Input" \
    --output_dir "/media/user/PortableSSD/Output" \
    --step all --n_procs 4
```

---

### Results & QC Exporter (`export_results.py`)

Generates publication-quality PDF reports summarizing anatomical normalization, first-level GLM activations, and `@chauffeur_afni` axial montage figures.

```bash
# Export QC PDFs for all subjects to default reports directory
python tim_analysis/export_results.py

# Export QC PDFs for specific subjects to custom destination
python tim_analysis/export_results.py --subject sub-435 sub-473 --output_dir "/media/user/VERBATIM SD/TIM/Output"
```

---

### Multi-Subject Report Merger (`concatenate_reports.py`)

Merges individual subject PDF reports into a single consolidated multi-subject PDF report:

```bash
python tim_analysis/concatenate_reports.py \
    --reports_dir "/media/user/VERBATIM SD/TIM/Output/reports" \
    --output "tim_consolidated_qc_report.pdf"
```

---

### HTML to PDF Converter (`convert_qc_to_pdf.py`)

Converts AFNI `afni_proc.py` Pythonic HTML review reports (`index.html`) to PDF format using headless Chrome or `wkhtmltopdf`:

```bash
python tim_analysis/convert_qc_to_pdf.py \
    --input "/path/to/sub-435_preproc.results/QC_sub-435/index.html" \
    --output "/path/to/sub-435_preproc_qc.pdf"
```

---

### Ledalab ERA Timing Converter (`era_to_timing.py`)

Extracts electrodermal SCR amplitudes from Ledalab Event-Related Analysis (ERA) exports:

```bash
python tim_analysis/era_to_timing.py \
    --era_path "/path/to/sub-435_era_export.txt" \
    --events_path "/path/to/sub-435/ses-1/func" \
    --output_path "/path/to/sub-435/ses-1/func/timings" \
    --blocks 5
```

---

### DICOM to BIDS Converter (`mri_file_preprocess.py`)

Organizes raw Siemens MRI console DICOM directories into BIDS-compliant NIfTI layout using `dcm2niix`:

```bash
python tim_analysis/mri_file_preprocess.py \
    --dicom_dir "/path/to/raw_dicoms" \
    --bids_dir "/path/to/BIDS_input" \
    --subject "sub-435" \
    --session 1
```

---

## Output Directory Structure

```text
/output_dir/
├── sub-435/
│   └── ses-1/
│       ├── anat_warped/                      # Output from 01_preprocess_anat.sh
│       │   ├── anatSS.sub-435.nii            # Skull-stripped anatomical in native space
│       │   ├── anatQQ.sub-435.nii            # Non-linearly warped anatomical in MNI space
│       │   ├── anatQQ.sub-435.aff12.1D       # Affine matrix to MNI
│       │   └── anatQQ.sub-435_WARP.nii       # Non-linear warp displacement field
│       ├── func_preproc/                     # Output from 02_preprocess_func.sh
│       │   └── sub-435_preproc.results/
│       │       ├── pb05.sub-435_preproc.r01.scale+tlrc.HEAD # Scaled functional bricks
│       │       ├── dfile_rall.1D             # Motion parameters across all runs
│       │       ├── censor_sub-435_combined_2.1D # Combined motion and outlier censor vector
│       │       ├── mask_epi_anat.sub-435+tlrc.HEAD # Intersection EPI-anatomical mask
│       │       └── QC_sub-435/               # APQC HTML quality control directory
│       └── glm/                              # Output from 03_run_glm.sh
│           ├── pain_by_rating/
│           │   ├── stats.sub-435_pain_by_rating+tlrc.HEAD # Full statistical sub-bricks
│           │   ├── fitts.sub-435_pain_by_rating+tlrc.HEAD # Full model fit
│           │   ├── errts.sub-435_pain_by_rating+tlrc.HEAD # Residual timeseries
│           │   └── QC/                       # @chauffeur_afni 3x3 axial montage PNGs
│           └── ...
└── group_analysis/                           # Output from 04_run_group_analysis.sh
    └── pain_by_rating/
        └── pain_by_rating/
            ├── result_pain_by_rating+tlrc.HEAD # 3dttest++ or 3dLMEr group statistics
            ├── group_mask+tlrc.HEAD          # Overlap mask across included subjects
            └── result_pain_by_rating_images/ # Publication montage figures
```

---

## Quality Control & Verification

Every subject execution produces comprehensive visual inspection artifacts:
1. **APQC Pythonic Review**: Located in `func_preproc/sub-XXX_preproc.results/QC_sub-XXX/index.html`. Inspects slice timing, motion spikes, registration overlays, and tSNR maps.
2. **Chauffeur QC Axial Montages**: Rendered automatically by `03_run_glm.sh` using `@chauffeur_afni`. Produces 3x3 axial montage slices with clusterization (`-NN 2 -clust_nvox 35`) and dual-sided thresholding ($p < 0.05$).
3. **Automated Unit Testing**: The entire command builder and timing generation logic is verified via:
   ```bash
   python3 -m unittest discover -s tests -v
   ```
