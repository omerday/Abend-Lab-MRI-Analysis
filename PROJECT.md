# Project: Abend Lab fMRI Analysis Refactoring & Invariance Verification

## Architecture
The repository consists of two isolated neuroimaging pipeline packages (`tim_analysis/` and `war_analysis/`), a cloud execution subsystem (`cloud/`), an asynchronous remote monitoring daemon (`remote_monitor/`), and a unified testing framework (`tests/`).

```
Abend-Lab-MRI-Analysis/
├── tim_analysis/             # TIM Pipeline (thermal pain & anticipation paradigm)
│   ├── run_analysis.py       # Main batch controller & CLI runner
│   ├── export_results.py     # Results & QC PDF exporter to Dropbox/cloud
│   ├── concatenate_reports.py# Multi-subject QC PDF merger
│   ├── convert_qc_to_pdf.py  # Headless HTML-to-PDF report generator
│   ├── era_to_timing.py      # Ledalab ERA to AFNI 1D timing converter
│   ├── mri_file_preprocess.py# Raw DICOM/NIfTI BIDS organizer
│   ├── analysis_configs/     # main_config.toml & analysis_models.toml
│   └── scripts/              # 00-04 AFNI shell processing scripts
├── war_analysis/             # WAR Pipeline (threat appraisal & regulation paradigm)
│   ├── run_analysis.py       # Main batch controller & CLI runner
│   ├── export_results.py     # Results & QC PDF exporter
│   ├── concatenate_reports.py# Multi-subject QC PDF merger
│   ├── utils/                # convert_qc_to_pdf, create_tr_magnitude_file, process_era_files, etc.
│   ├── analysis_configs/     # main_config.toml & analysis_models.toml
│   └── scripts/              # 00-04 AFNI shell processing scripts
├── cloud/                    # Cloud Batch & GCS execution infrastructure
│   ├── gcs_helper.py         # GCS sync, download, upload, sharding, staging
│   ├── entrypoint.sh         # Docker container runtime entrypoint
│   ├── workflow.yaml         # Google Cloud Workflows orchestration definition
│   └── batch_job_template.json # Google Cloud Batch job specifications
├── remote_monitor/           # Telegram bot & workstation monitoring daemon
│   ├── bot.py                # Asynchronous Telegram bot interface
│   ├── pipeline_manager.py   # Background job tracker and runner
│   ├── system_monitor.py     # System metrics and AFNI process inspection
│   ├── notify.py             # Lightweight stdlib Telegram webhook client
│   └── config.py             # Bot configuration parser & validator
└── tests/                    # Comprehensive unittest regression test suite
    ├── run_all_tests.py      # Test suite discovery runner
    ├── test_configs.py       # Configuration parsing & schema validation tests
    ├── test_gcs_helper.py    # GCS URI parsing, path join, and task sharding tests
    ├── test_system_monitor.py# Metric formatting and log tail classification tests
    ├── test_timings_math.py  # 100% mathematical equivalence of timing calculations
    ├── test_afni_commands.py # First-level and group-level AFNI command invariance tests
    └── test_controllers.py   # CLI interface and backward compatibility tests
```

## Feature Inventory
Every feature and constraint identified across the survey is cataloged and assigned to a specific milestone.

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Directory Isolation | Enforce complete separation between `tim_analysis/` and `war_analysis/`; zero cross-imports | M1 | Survey E1, R1 |
| 2 | Python Controller Refactoring | Refactor `run_analysis.py`, `export_results.py`, `concatenate_reports.py`, `convert_qc_to_pdf.py`, `mri_file_preprocess.py` with PEP 8, types, and modular functions | M1 | Survey E1, R1 |
| 3 | Timing Scripts Refactoring | Standardize `era_to_timing.py`, `process_era_files.py`, `create_tr_magnitude_file.py`, removing `quit()`, bare excepts, and deprecations | M1 | Survey E1, R1 |
| 4 | Dead Code & Path Removal | Remove `removing_files.py`, tracked `.pyc` files, personal `/Users/omerdayan/Downloads` paths, and parameterize hardcoded configs | M1 | Survey E1, R1 |
| 5 | Shell Scripts Standardization | Refactor 00-04 shell scripts in TIM and WAR: `set -euo pipefail`, ShellCheck compliance, fix `$?` and unbound variable bugs, uniform logging | M2 | Survey E1, R1 |
| 6 | AFNI Command Invariance | Guarantee exact flag, argument, parameter, and dataset order for `sswarper2`, `afni_proc.py`, `3dttest++`, `3dLMEr` across all models | M2 | Survey E1, R2 |
| 7 | Mathematical Timing Invariance | Ensure 100% identical math for event onsets, durations, amplitude modulations (TIM *2/*6/*8, WAR images/blocks/rest), and SCR binning (11 TRs, 28s lag) | M1, M2 | Survey E1, E3, R2 |
| 8 | Cloud Subsystem Hardening | Fix `cloud/gcs_helper.py` unhandled storage fallback exception in `gcs_sync_up`, align `EXPORT_QC_PDFS` default in `cloud/entrypoint.sh`, type hints & clean exceptions | M3 | Survey E2, R3 |
| 9 | Remote Monitor Hardening | Refactor `bot.py`, `pipeline_manager.py`, `system_monitor.py`, `notify.py`, `config.py`; fix Telegram markdown escaping; clean async architecture | M3 | Survey E2, R3 |
| 10 | Standalone Unit Test Framework | Implement standard library `unittest` suite in `tests/` requiring zero pip installations, supporting Python 3.8 through 3.13 | E2E Track | Survey E3, R4 |
| 11 | Tier 1: Feature Coverage Tests | >=5 test cases per feature for configs, GCS helper, system monitor, timing generators, command builders | E2E Track | Survey E3, R4 |
| 12 | Tier 2: Boundary & Corner Cases | Boundary tests for timing files (0, negative, max TRs, lag=28 vs 0), GCS URIs (trailing slashes, spaces, missing prefix), sharding edge cases | E2E Track | Survey E3, R4 |
| 13 | Tier 3: Cross-Feature Combinations | Pairwise tests: model type combinations (`3dttest++` vs `3dLMEr`), session configurations (`has_scr=True/False`), CLI overrides with env vars | E2E Track | Survey E3, R4 |
| 14 | Tier 4: Real-World Scenarios | End-to-end golden verification of AFNI command generation and timing file generation matching baseline golden vectors | E2E Track | Survey E3, R4 |
| 15 | Tier 5: Adversarial Hardening | White-box stress testing, mutant testing, and edge case coverage hardening | M5 | Survey E3, R4 |
| 16 | Neuroimaging Documentation | Comprehensive root `README.md`, subfolder READMEs, and inline documentation of all AFNI parameters (TR=2.0s, echo times, blur sizes, censoring, SSW costs) | M4 | Survey E1, E3, R5 |
| 17 | Operational Safety Enforcement | Zero git commits (`git commit`), zero remote pushes, zero GCP deployments or Cloud Batch job submissions | All | Survey E2, R6 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Design and implement complete opaque-box regression test suite in `tests/` (Tiers 1-4) | none | DONE |
| M1 | Pipeline Python Refactoring & Isolation | Refactor all Python controllers & timing scripts in `tim_analysis/` and `war_analysis/`, remove dead code & personal paths | none | DONE |
| M2 | Shell Scripts Refactoring & Command Invariance | Refactor shell scripts 00-04 in TIM & WAR with `set -euo pipefail`, ensure 100% AFNI command and timing invariance | M1 | DONE |
| M3 | Cloud & Remote Monitor Subsystem Maintenance | Refactor and harden `cloud/` and `remote_monitor/` components, fix GCS fallback exception & Telegram escaping | none | DONE |
| M4 | Comprehensive Documentation & Parameter Transparency | Author root `README.md`, update subfolder READMEs, add detailed AFNI neuroimaging parameter rationale and docstrings | M1, M2, M3 | DONE |
| M5 | Final Verification & Adversarial Hardening | Pass 100% of E2E tests (Tiers 1-4) and execute Tier 5 adversarial coverage hardening | E2E, M1, M2, M3, M4 | DONE |

## Interface Contracts

### TIM & WAR Controllers CLI Contract
- CLI Flags for `run_analysis.py`:
  - `--step`: choices `["create_timings", "preprocess_anat", "preprocess_func", "run_glm", "run_group_analysis", "all_first_level", "all"]`
  - `--subject`: string subject ID (e.g. `sub-435`, `sub-AL01`) or `all`
  - `--analysis`: model name defined in `analysis_models.toml` or `all`
  - `--group_model`: group analysis model name or `all`
  - `--session`: session index integer (optional)
  - `--n_procs`: number of parallel worker processes (default 4)
  - `--scratch_dir`: custom scratch directory path
  - `--clean_scratch`: boolean flag to clean scratch space upon completion
- Environment Variable Contract:
  - `MRI_INPUT_DIR`: overrides `input_dir` in `main_config.toml`
  - `MRI_OUTPUT_DIR`: overrides `output_dir` in `main_config.toml`
  - `MRI_REPORTS_DIR`: overrides report destination
  - `KEEP_PB00_PB04`: if `"1"`, disables deletion of intermediate functional preprocessing bricks

### Shell Script Parameters Contract
All scripts (`00_create_timings.sh`, `01_preprocess_anat.sh`, `02_preprocess_func.sh`, `03_run_glm.sh`, `04_run_group_analysis.sh`) must accept arguments using standard positional or flag patterns:
- Invariance: Command syntax passed to AFNI (`afni_proc.py`, `sswarper2`, `3dttest++`, `3dLMEr`) MUST be character-for-character identical in generated option flags.

### Cloud GCS Helper Contract
- `is_gcs_uri(path: Optional[str]) -> bool`: returns True iff path starts with `"gs://"`
- `normalize_gcs_uri(uri: str) -> str`: strips whitespace and trailing slashes, preserving `"gs://"`
- `join_uri(base: str, *parts: str) -> str`: joins local or GCS URI parts seamlessly
- `get_cloud_task_shard() -> Tuple[Optional[int], Optional[int]]`: parses task index and count from Batch/Cloud Run env vars
- `shard_subjects_for_cloud_task(subjects: List[str]) -> List[str]`: shards subjects via `subjects[idx::total]`

## Code Layout
- `.agents/teamwork/`: Metadata, plans, progress, and handoffs only.
- `tim_analysis/`: TIM Python controllers, `analysis_configs/`, and `scripts/`.
- `war_analysis/`: WAR Python controllers, `utils/`, `analysis_configs/`, and `scripts/`.
- `cloud/`: Cloud execution scripts, Dockerfile, workflow specs.
- `remote_monitor/`: Async Telegram monitoring bot and utilities.
- `tests/`: Pure Python `unittest` test suite and golden regression benchmarks.
