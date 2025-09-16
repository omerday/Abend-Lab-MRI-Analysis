
# fMRI Analysis Pipeline

This project provides a modular, configurable, and reproducible pipeline for conducting first-level and group-level fMRI analyses, built primarily around AFNI.

---

## Table of Contents
- [Prerequisites](#prerequisites)
- [Directory Structure](#directory-structure)
- [Configuration](#configuration)
  - [Main Configuration](#main-configuration)
  - [Analysis Model Configuration](#analysis-model-configuration)
- [Workflow](#workflow)
  - [First-Level Analysis](#first-level-analysis)
  - [Group-Level Analysis](#group-level-analysis)
- [Advanced Usage](#advanced-usage)
  - [Adding a New Analysis Model](#adding-a-new-analysis-model)
  - [Running Specific Subjects](#running-specific-subjects)

---

## Prerequisites

1.  **AFNI**: The core analysis software. Ensure that AFNI commands (`afni_proc.py`, `3dttest++`, etc.) are available in your shell's path.
2.  **Python 3**: The pipeline's controller scripts are written in Python.
3.  **TOML Library**: The configuration files use the TOML format. Install the Python library:
    ```bash
    pip install toml
    ```

---

## Directory Structure

The ecosystem is organized to separate logic, configuration, and results.

```
/tim_analysis/
├── analysis_configs/     # All pipeline configuration files.
│   ├── main_config.toml
│   └── analysis_models.toml
├── logs/                 # Log files for each processing step.
├── old_scripts/          # The original, refactored scripts.
├── scripts/
│   ├── 00_create_timings.sh
│   ├── 01_preprocess_anat.sh
│   ├── 02_preprocess_func.sh
│   ├── 03_run_glm.sh
│   └── run_group_analysis.sh
├── run_analysis.py       # Controller for all FIRST-LEVEL analyses.
├── run_group_level.py    # Controller for all GROUP-LEVEL analyses.
└── README.md             # This file.
```

---

## Configuration

The entire pipeline is controlled by two main configuration files located in `analysis_configs/`.

### Main Configuration

The `main_config.toml` file contains global settings for the entire pipeline.

**IMPORTANT**: You must edit the `input_dir` and `output_dir` paths in this file before running the pipeline for the first time.

```toml
# Absolute path to the directory containing the raw BIDS data.
input_dir = "/path/to/your/bids_data"

# Absolute path to the directory where all outputs (derivatives) will be saved.
output_dir = "/path/to/your/derivatives"

# Default list of all subjects to be processed.
all_subjects = ["sub-001", "sub-002", "sub-003"]
```

### Analysis Model Configuration

The `analysis_models.toml` file defines the specific parameters for each first-level GLM variation. You can add, remove, or modify analyses here without changing any code.

*Example: A simple model for pain ratings.*
```toml
[pain_by_rating]
description = "Pain period amplitude modulated by subjective rating."
stim_files = ["timings/pain_rating_amp.1D"]
stim_labels = ["PAIN"]
basis = "BLOCK(4,1)"
glt = [] # No general linear tests for this model
```

*Example: A model that only applies to specific subjects.*
```toml
[special_anticipation_model]
description = "A special model for a subset of subjects."
stim_files = ["timings/anticipation_scr_amp.1D"]
stim_labels = ["SCR"]
basis = "BLOCK(2,1)"
# This analysis will ONLY run for sub-002 and sub-005.
subjects = ["sub-002", "sub-005"]
```

---

## Workflow

### First-Level Analysis

All first-level analyses are managed by the `run_analysis.py` script. It provides a step-by-step workflow from timing file generation to the final GLM.

**Key Steps:**
1.  `create_timings`: Generates AFNI-compatible `.1D` files from your event `.tsv` files.
2.  `preprocess_anat`: Runs anatomical preprocessing (`sswarper2`).
3.  `preprocess_func`: Runs functional preprocessing (`tshift`, `volreg`, `blur`, etc.).
4.  `glm`: Runs the final regression analysis for a specific model.

**Example Usage:**

*   **Run a single step for one subject:**
    ```bash
    python run_analysis.py --subject sub-001 --step create_timings
    python run_analysis.py --subject sub-001 --step preprocess_anat
    ```

*   **Run a specific GLM analysis for one subject (assumes preprocessing is complete):**
    ```bash
    python run_analysis.py --subject sub-001 --analysis pain_by_rating --step glm
    ```

*   **Run the ENTIRE pipeline for an analysis (for all its relevant subjects):**
    ```bash
    python run_analysis.py --analysis pain_by_rating --step all
    ```

*   **Run in Parallel**: To speed up processing, use the `--n_procs` argument. The command below runs the full pipeline for the `pain_by_rating` analysis across all its subjects, using 4 cores.
    ```bash
    python run_analysis.py --analysis pain_by_rating --step all --n_procs 4
    ```

### Group-Level Analysis

Group-level analyses are managed by the separate `run_group_level.py` script.

**Output Location**: Results are saved to `{output_dir}/group/{analysis_name}/{group_label}/`.

**Example Usage:**

Let's say you want to run a group analysis on the `pain_by_rating` model. You need to specify which contrast from that model you want to test (e.g., the coefficient for the `PAIN` regressor, which is `PAIN#0_Coef`).

```bash
python run_group_level.py \
    --analysis pain_by_rating \
    --contrast "PAIN#0_Coef" \
    --label "all_subjects_vs_baseline"
```

This will:
1.  Find all subjects associated with the `pain_by_rating` analysis.
2.  Collect their resulting `stats...HEAD` files.
3.  Run `3dttest++` on the `PAIN#0_Coef` sub-brick.
4.  Save the results to `{output_dir}/group/pain_by_rating/all_subjects_vs_baseline/`.

---

## Advanced Usage

### Adding a New Analysis Model

To add a new first-level analysis, simply open `analysis_configs/analysis_models.toml` and add a new entry. For example:

```toml
[my_new_model]
description = "A new model testing X vs Y."
stim_files = ["timings/X.1D", "timings/Y.1D"]
stim_labels = ["X", "Y"]
basis = "BLOCK(2,1)"
glt = [{ sym = "X - Y", label = "X-Y_contrast" }]
```

You can then run it immediately:
`python run_analysis.py --analysis my_new_model --step all`

### Running Specific Subjects

Both `run_analysis.py` and `run_group_level.py` accept a `--subjects` argument to override the configuration files. This is useful for testing or running on a specific subset.

```bash
# Run GLM for only two subjects, regardless of config
python run_analysis.py --analysis pain_by_rating --step glm --subjects sub-001,sub-004

# Run group analysis on a hand-picked group
python run_group_level.py --analysis pain_by_rating --contrast "PAIN#0_Coef" --label "custom_group" --subjects sub-001,sub-004,sub-008
```
