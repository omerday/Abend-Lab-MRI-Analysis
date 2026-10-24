# Abend Lab fMRI Analysis Suite

[![AFNI Version](https://img.shields.io/badge/AFNI-24.x%2B-blue.svg)](https://afni.nimh.nih.gov/)
[![Python Version](https://img.shields.io/badge/Python-3.8%20|%203.9%20|%203.10%20|%203.11%20|%203.12%20|%203.13-brightgreen.svg)](https://www.python.org/)
[![Test Suite](https://img.shields.io/badge/Tests-90%2F90%20Passing-success.svg)](tests/)
[![Architecture](https://img.shields.io/badge/Cloud-GCP%20Batch%20%7C%20Workflows-orange.svg)](cloud/)
[![ChatOps](https://img.shields.io/badge/Remote%20Monitor-Telegram%20Bot-blueviolet.svg)](remote_monitor/)

A production-grade, modular, and mathematically verified neuroimaging analysis ecosystem developed for the **Abend Lab for Neuroscience of Psychopathology**. The repository provides end-to-end processing pipelines for two complex task paradigms:
1. **TIM (Thermal Anticipation & Pain)**: Thermal pain delivery, anticipation cues, subjective pain rating modulation, and electrodermal skin conductance (SCR).
2. **WAR (Threat Appraisal & Emotion Regulation)**: Emotional block and image reactivity, 28-second initial lag blocks, 11-bin block autonomic SCR expansions, and linear mixed-effects modeling.

The ecosystem includes full support for **local multi-core workstation execution**, **massively parallel serverless batch processing on Google Cloud Platform (GCP)**, **asynchronous mobile monitoring (ChatOps)** via Telegram, and a **comprehensive 90-test automated regression test suite** built exclusively on Python's standard library.

---

## ⚠️ Operational Safety & Compliance Notice

> **MANDATORY POLICY**:
> Under NO circumstances should automated scripts or agents commit changes to git repositories (`git commit`), push to remote repositories (`git push`), or deploy/submit jobs to Google Cloud Platform (`gcloud batch jobs submit`, `gcloud builds submit`).
> All version control operations and cloud deployments are strictly managed by designated human researchers.

---

## Table of Contents
- [System Architecture](#system-architecture)
- [Repository Structure](#repository-structure)
- [Neuroimaging Paradigms](#neuroimaging-paradigms)
  - [TIM Task: Thermal Anticipation & Pain](#tim-task-thermal-anticipation--pain)
  - [WAR Task: Threat Appraisal & Regulation](#war-task-threat-appraisal--regulation)
- [AFNI Neuroimaging Parameter Transparency](#afni-neuroimaging-parameter-transparency)
- [Developer Quickstart](#developer-quickstart)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Installation & Setup](#2-installation--setup)
  - [3. Running the Regression Test Suite](#3-running-the-regression-test-suite)
- [CLI Usage Guide](#cli-usage-guide)
  - [TIM Pipeline (`tim_analysis/run_analysis.py`)](#tim-pipeline-tim_analysisrun_analysispy)
  - [WAR Pipeline (`war_analysis/run_analysis.py`)](#war-pipeline-war_analysisrun_analysispy)
  - [Global Environment Variable Overrides](#global-environment-variable-overrides)
- [Cloud Execution Subsystem (GCP Batch & Workflows)](#cloud-execution-subsystem-gcp-batch--workflows)
- [Remote Monitor & ChatOps Daemon (Telegram Bot)](#remote-monitor--chatops-daemon-telegram-bot)
- [Automated Testing Framework](#automated-testing-framework)
- [License & Citation](#license--citation)

---

## System Architecture

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      Raw Neuroimaging Inputs                           │
 │     Local BIDS Directory  OR  GCS Bucket (gs://.../inputs/<task>/)     │
 └───────────────────┬────────────────────────────────┬───────────────────┘
                     │                                │
                     ▼                                ▼
 ┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
 │     TIM Pipeline (tim_analysis/)     │  │     WAR Pipeline (war_analysis/)     │
 │  00_create_timings.sh                │  │  00_create_timings.sh                │
 │    - Visual cue timing (*2/*6/*8)    │  │    - 28s initial lag adjustment      │
 │    - Ledalab ERA SCR integration     │  │    - 11-bin block TR expansion       │
 │  01_preprocess_anat.sh               │  │  01_preprocess_anat.sh               │
 │    - sswarper2 non-linear (lpa)      │  │    - sswarper2 non-linear (lpa)      │
 │  02_preprocess_func.sh               │  │  02_preprocess_func.sh               │
 │    - afni_proc.py multi-echo (OC)    │  │    - afni_proc.py multi-echo (OC)    │
 │    - pb00-pb04 auto-cleanup          │  │    - pb00-pb04 auto-cleanup          │
 │  03_run_glm.sh                       │  │  03_run_glm.sh                       │
 │    - First-level GLM + @chauffeur    │  │    - First-level GLM + @chauffeur    │
 │  04_run_group_analysis.sh            │  │  04_run_group_analysis.sh            │
 │    - 3dttest++ (-clustsim) / 3dLMEr  │  │    - 3dLMEr (3dClustSim ACF) / 3dttest│
 └───────────────────┬──────────────────┘  └──────────────────┬───────────────────┘
                     │                                        │
                     └───────────────────┬────────────────────┘
                                         ▼
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │                        Derivatives & Quality Control                           │
 │  - Statistical Sub-Bricks (stats.*+tlrc), Model Fits (fitts), Residuals (errts)│
 │  - High-Resolution @chauffeur_afni Axial Montages                              │
 │  - Consolidated QC PDFs (export_results.py & concatenate_reports.py)            │
 └───────────────────┬────────────────────────────────┬───────────────────────────┘
                     │                                │
                     ▼                                ▼
 ┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐
 │    Cloud Execution Subsystem (cloud/)│  │ Remote Monitor Daemon (remote_monitor)│
 │  - Google Cloud Batch / Cloud Run    │  │  - Async Telegram ChatOps Bot        │
 │  - Worker Sharding [idx::total]      │  │  - Milestone Alerts & Brain Montages │
 │  - 1-Click Cloud Workflows (GCP UI)  │  │  - Live Hardware Health & Log Tails  │
 └──────────────────────────────────────┘  └──────────────────────────────────────┘
                     ▲
                     │
 ┌───────────────────┴────────────────────────────────────────────────────────────┐
 │                     Automated Regression Test Suite (tests/)                   │
 │   90/90 Passing Tests (Pure Python unittest, zero external dependencies)       │
 │   Configs, GCS Sharding, Hardware Metrics, Timing Math, AFNI Commands, CLI     │
 └────────────────────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```text
Abend-Lab-MRI-Analysis/
├── README.md                       # Master project documentation (this file)
├── PROJECT.md                      # Architecture specifications and interface contracts
├── TEST_READY.md                   # Regression test suite verification report
├── tim_analysis/                   # Thermal Anticipation & Pain pipeline
│   ├── run_analysis.py             # Main Python CLI controller
│   ├── export_results.py           # QC and statistical PDF report exporter
│   ├── concatenate_reports.py      # Multi-subject PDF merger
│   ├── convert_qc_to_pdf.py        # APQC HTML to PDF converter
│   ├── era_to_timing.py            # Ledalab ERA electrodermal timing parser
│   ├── mri_file_preprocess.py      # Siemens DICOM to BIDS converter
│   ├── analysis_configs/           # main_config.toml & analysis_models.toml
│   ├── scripts/                    # ShellCheck-compliant AFNI scripts (00-04)
│   └── README.md                   # TIM-specific pipeline documentation
├── war_analysis/                   # Threat Appraisal & Emotion Regulation pipeline
│   ├── run_analysis.py             # Main Python CLI controller (first-level & group)
│   ├── export_results.py           # QC and statistical PDF report exporter
│   ├── concatenate_reports.py      # Multi-subject PDF merger
│   ├── utils/                      # Timing, ERA, and BIDS helper utilities
│   │   ├── create_tr_magnitude_file.py # TR magnitude generator (28s lag math)
│   │   ├── process_era_files.py    # 11-bin block expansion & image SCR parser
│   │   ├── mri_file_preprocess.py  # DICOM to BIDS converter
│   │   ├── convert_qc_to_pdf.py    # APQC HTML to PDF converter
│   │   └── rename_subjects.py      # Subject naming normalizer
│   ├── analysis_configs/           # main_config.toml & analysis_models.toml
│   ├── scripts/                    # ShellCheck-compliant AFNI scripts (00-04)
│   └── README.md                   # WAR-specific pipeline documentation
├── cloud/                          # GCP Cloud Batch & Workflows deployment
│   ├── gcs_helper.py               # GCS URI parsing, sharding, and staging
│   ├── entrypoint.sh               # Docker container runtime entrypoint
│   ├── workflow.yaml               # Google Cloud Workflows browser execution spec
│   ├── batch_job_template.json     # Cloud Batch task array configuration
│   ├── Dockerfile                  # Container definition with AFNI and dependencies
│   └── README.md                   # GCP deployment and operations guide
├── remote_monitor/                 # Asynchronous Telegram bot & ChatOps daemon
│   ├── bot.py                      # Async Telegram bot controller
│   ├── pipeline_manager.py         # Subprocess runner & process tree manager
│   ├── system_monitor.py           # CPU, RAM, disk, and AFNI process inspector
│   ├── notify.py                   # Standalone CLI/webhook Telegram notifier
│   ├── config.py                   # TOML config parser & whitelist validator
│   ├── bot_config.template.toml    # Bot configuration template
│   ├── mri_bot.service             # Systemd 24/7 service unit file
│   └── README.md                   # Bot setup and operation guide
└── tests/                          # Unified regression test suite
    ├── run_all_tests.py            # Standard test discovery runner
    ├── test_configs.py             # TOML configuration & schema tests (15 tests)
    ├── test_gcs_helper.py          # GCS URI parsing & sharding tests (17 tests)
    ├── test_system_monitor.py      # Hardware formatting & log parsing tests (14 tests)
    ├── test_timings_math.py        # 100% mathematical timing equivalence (16 tests)
    ├── test_afni_commands.py       # AFNI command string invariance tests (15 tests)
    └── test_controllers.py         # CLI parsing & step expansion tests (13 tests)
```

---

## Neuroimaging Paradigms

### TIM Task: Thermal Anticipation & Pain
- **Research Question**: Neural encoding of prospective pain anticipation versus nociceptive pain delivery.
- **Paradigm Structure**:
  - Color-coded visual cues predicting upcoming thermal intensities: Green ($\times 2$), Yellow ($\times 6$), Red ($\times 8$).
  - Pre-heat anticipation window.
  - Thermal pain delivery via contact thermode.
  - Continuous subjective pain intensity rating.
  - Concomitant electrodermal activity (SCR) integrated via Ledalab ERA amplitude modulations (`stim_types = "AM2"`).

### WAR Task: Threat Appraisal & Regulation
- **Research Question**: Emotion regulation and autonomic reactivity to threatening vs. neutral stimuli across clinical cohorts (e.g. MDMA vs. Control).
- **Paradigm Structure**:
  - Emotional blocks (22-second duration): Negative, Positive, Neutral scenes, and interleaved rest periods.
  - Image events (4-second duration).
  - **28-Second Initial Lag Blocks**: First 28 seconds (14 TRs at TR=2.0s) of each run serve as baseline stabilization. `create_tr_magnitude_file.py` shifts event times by 28 seconds, yielding exactly 286 TRs (versus 300 TRs for `lag = 0`).
  - **11-Bin TR Expansion**: Each emotional block start expands into 11 consecutive 2.0-second TR bins ($t, t+2, \dots, t+20$), tracking continuous autonomic arousal trajectories without assuming canonical hemodynamic profiles.

---

## AFNI Neuroimaging Parameter Transparency

Both pipelines adhere to rigorous, mathematically verified AFNI parameter standards:

| Parameter | Value | Scope | Methodological & Physical Rationale |
| :--- | :--- | :--- | :--- |
| **Repetition Time (TR)** | `2.0 s` | TIM & WAR | Sampling frequency $f_s = 0.5$ Hz ($f_{\text{Nyq}} = 0.25$ Hz). Matches multi-slice EPI readouts and discrete behavioral event grids (4s images = 2 TRs, 22s blocks = 11 TRs). |
| **Multi-Echo Echo Times** | `13.6, 25.96, 38.3 ms` | TIM & WAR | Captures transverse relaxation decay across varying baseline $T_2^*$. Short echo recovers signal in ventral prefrontal cortex and amygdala; long echoes maximize sensitivity in dorsal cortex. |
| **Echo Combination** | `combine_method OC` | TIM & WAR | Optimal Combination calculates voxel-wise $T_2^*$ weights: $w(TE_m) \propto TE_m \cdot e^{-TE_m / T_2^*}$. Maximizes Contrast-to-Noise Ratio (CNR) and suppresses thermal noise. |
| **Anatomical Alignment** | `sswarper2` | TIM & WAR | Dual skull-stripping and non-linear template warping to `MNI152_2009_template_SSW.nii.gz`. Prevents skull-stripping failures in clinical populations. |
| **SSWarper Cost Function** | `-cost_nl_final lpa` | TIM & WAR | Local Pearson Correlation computes correlation in moving local patches. Provides superior resistance to $B_1$ field inhomogeneities and localized RF coil shading. |
| **Spatial Smoothing** | `4.0 mm FWHM` | TIM & WAR | Isotropic Gaussian kernel. Preserves anatomical boundaries within small subcortical nuclei (amygdala subnuclei, dorsal posterior insula) without signal bleeding into ventricles or white matter. |
| **Motion Censoring** | `0.5 mm` | TIM & WAR | Euclidean norm threshold: $\text{enorm}_t = \sqrt{\sum (\Delta \text{motion}_t)^2}$. Scrubbed TRs prevent false-positive activation driven by stimulus-correlated head motion. |
| **Outlier Censoring** | `0.05 (5%)` | TIM & WAR | Computed via `3dToutcount`. TRs with $>5\%$ whole-brain automasked voxels exceeding trended MAD deviations are scrubbed to eliminate transient breath-holding or RF spikes. |
| **Storage Optimization** | `KEEP_PB00_PB04=0` | TIM & WAR | Purges intermediate functional bricks (`pb00`–`pb04`) to save 15–20 GB per subject, while strictly preserving scaled bricks (`pb05`), motion regressors, censor files, fits, residuals, and GLM outputs. |

---

## Developer Quickstart

### 1. Prerequisites
- **AFNI**: Installed and accessible on your shell `PATH` (`which afni_proc.py`, `which sswarper2`).
- **Python**: Version 3.8 through 3.13.
- **R**: Installed with `lme4`, `afex`, and `phia` packages (required for `3dLMEr` group models).
- **dcm2niix**: (Optional) Required for DICOM-to-BIDS conversion.

### 2. Installation & Setup
Clone the repository:
```bash
git clone https://github.com/Abend-Lab/Abend-Lab-MRI-Analysis.git
cd Abend-Lab-MRI-Analysis
```

Create a virtual environment and install optional reporting dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r tim_analysis/requirements.txt
```

### 3. Running the Regression Test Suite
Verify your installation immediately using Python's built-in `unittest` framework (zero pip packages required):
```bash
python3 -m unittest discover -s tests -v
```
**Expected Result**: All 90 unit and regression tests pass with 0 errors and 0 failures.

---

## CLI Usage Guide

### TIM Pipeline (`tim_analysis/run_analysis.py`)

```bash
# 1. Run all preprocessing for a single subject
python tim_analysis/run_analysis.py --subject sub-435 --step preprocess

# 2. Run first-level GLM across 4 CPU cores
python tim_analysis/run_analysis.py --step glm --analysis pain_by_rating --n_procs 4

# 3. Run complete first-level pipeline for multiple subjects in parallel
python tim_analysis/run_analysis.py --subject sub-435 sub-473 sub-489 --step all --n_procs 3

# 4. Run group-level analysis (3dttest++ with -clustsim)
python tim_analysis/run_analysis.py --step group_analysis --analysis pain_by_rating --group_model pain_by_rating

# 5. Export QC PDFs to reports directory
python tim_analysis/export_results.py --subject sub-435
```

### WAR Pipeline (`war_analysis/run_analysis.py`)

```bash
# 1. Run all preprocessing for a single subject
python war_analysis/run_analysis.py --subject sub-AL01 --step preprocess

# 2. Run first-level GLM for emotional block model
python war_analysis/run_analysis.py --step glm --analysis by_block --n_procs 4

# 3. Run group analysis (3dLMEr linear mixed-effects)
python war_analysis/run_analysis.py --step group_analysis --analysis by_block --group_model mdma_vs_control_s1

# 4. Run group analysis (3dttest++ one-sample t-test)
python war_analysis/run_analysis.py --step group_analysis --analysis by_block --group_model mdma_s1_neg_vs_neut

# 5. Export QC PDFs to reports directory
python war_analysis/export_results.py --subject sub-AL01
```

### Global Environment Variable Overrides

All filesystem paths can be redirected dynamically without editing TOML files:
```bash
export MRI_INPUT_DIR="/media/user/PortableSSD/RawBIDS"
export MRI_OUTPUT_DIR="/media/user/PortableSSD/Derivatives"
export MRI_REPORTS_DIR="/media/user/PortableSSD/Reports"
export KEEP_PB00_PB04="0"  # Set to "1" only if intermediate bricks are required

python tim_analysis/run_analysis.py --step all --n_procs 4
```

---

## Cloud Execution Subsystem (GCP Batch & Workflows)

The `cloud/` subsystem enables one-click serverless batch execution on Google Cloud Platform:
- **Zero Local Hardware Needed**: Every subject VM is provisioned on demand with 8 vCPUs, 16 GB RAM, and high-speed NVMe storage.
- **Deterministic Subject Sharding**: Cloud Batch task index (`BATCH_TASK_INDEX`) automatically slices the subject list via `subjects[idx::total]`.
- **Spot VM Cost Reduction**: Supports `use_spot_vms: true` (~70% cost savings).
- **1-Click Web UI**: Trigger analyses directly from the Google Cloud Console Workflows UI:
  ```json
  {
    "job_name": "tim-cohort1-preproc-glm",
    "pipeline": "tim",
    "steps": ["preprocess", "glm"],
    "subjects": ["sub-435", "sub-473", "sub-489", "sub-499"],
    "analyses": ["pain_by_rating"],
    "use_spot_vms": true,
    "export_qc_pdfs": true,
    "parallelism": 10
  }
  ```
See [`cloud/README.md`](cloud/README.md) for full deployment instructions.

---

## Remote Monitor & ChatOps Daemon (Telegram Bot)

The `remote_monitor/` subsystem provides an asynchronous mobile management interface:
- **Outbound Long-Polling**: Connects to the Telegram Cloud API over TLS 443 with zero open firewall ports.
- **Whitelist Authorization**: Restricts access strictly to approved Telegram user IDs.
- **Milestone Push Alerts**: Dispatches updates as each individual subject completes, with `@chauffeur_afni` 3x3 axial montage PNGs attached.
- **Commands**:
  - `/status`: Real-time batch progress bar, running subjects, CPU/RAM utilization, and storage capacity.
  - `/run`: Interactive job launcher with inline buttons or shorthand syntax.
  - `/qa`: Download brain montages and APQC PDFs directly to your phone.
  - `/logs`: Tail the last 35 lines of recent execution logs.
  - `/kill`: Cancel running batch jobs safely.
- **Standalone Terminal Alerts**:
  ```bash
  python3 -m remote_monitor.notify \
      --message "✅ Subject <b>sub-435</b> completed GLM" \
      --photo "/path/to/PAIN#0.png"
  ```
See [`remote_monitor/README.md`](remote_monitor/README.md) for full configuration details.

---

## Automated Testing Framework

The repository is protected by a pure Python `unittest` regression suite located in `tests/`:

```bash
# Run the complete test suite with verbose output
python3 -m unittest discover -s tests -v

# Or use the discovery runner script
python3 tests/run_all_tests.py
```

### Test Coverage Breakdown (90 Tests Across 4 Tiers):
1. **Tier 1 (Feature Coverage — 36 Tests)**: Validates TOML parsing, GCS URI logic, hardware metrics, timing generators, and AFNI command builders.
2. **Tier 2 (Boundary & Corner Cases — 33 Tests)**: Tests edge cases including empty event lists, negative amplitudes, boundary TRs, zero/negative lags, malformed URIs, and missing configuration fields.
3. **Tier 3 (Cross-Feature Combinations — 12 Tests)**: Tests pairwise combinations of model types (`3dttest++` vs `3dLMEr`), session parameters (`has_scr=True/False`), CLI flag overrides, and complete partition invariance.
4. **Tier 4 (Golden Regression Verification — 9 Tests)**: Verifies exact character-for-character invariance of generated AFNI commands and numerical timing vectors against verified golden vectors.

---

## License & Citation

Developed for the **Abend Lab for Neuroscience of Psychopathology**.
When utilizing this codebase in academic publications, please cite the underlying neuroimaging software:
- **AFNI**: Cox, R.W. (1996). *AFNI: software for analysis and visualization of functional magnetic resonance neuroimages.* Computers and Biomedical Research, 29(3), 162-173.
- **Multi-Echo fMRI (OC)**: Posse, S., et al. (1999). *Enhancement of BOLD-contrast sensitivity by single-shot multi-echo functional MR imaging.* Magnetic Resonance in Medicine, 42(1), 87-97.
- **SSWarper**: Glen, D.R., et al. (2020). *Nonlinear registration with @SSwarper in AFNI.* NeuroImage, 222, 117246.
