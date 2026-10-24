# Google Cloud Platform (GCP) Execution Guide for TIM & WAR fMRI Pipelines

This directory contains the containerization, orchestration, and storage infrastructure for deploying and executing the Abend Lab's `tim_analysis` and `war_analysis` fMRI pipelines on **Google Cloud Platform (GCP)**. It leverages **Google Cloud Storage (GCS)**, **Google Cloud Batch** (or **Cloud Run Jobs**), and **Google Cloud Workflows** to enable fully automated, highly parallel, serverless batch processing directly from the GCP Console browser interface without requiring local hardware.

---

## ⚠️ Operational Safety & Compliance Notice

> **MANDATORY POLICY**:
> Under NO circumstances should automated scripts or agents submit jobs, trigger builds, or execute deployment commands (`gcloud builds submit`, `gcloud batch jobs submit`, `gcloud workflows execute`) directly against Google Cloud Platform.
> All builds and cloud job submissions must be reviewed and executed manually by the designated human project administrator.

---

## Table of Contents
- [Architecture & Processing Flow](#architecture--processing-flow)
- [GCS Bucket Organization](#gcs-bucket-organization)
- [Environment Variables & Configuration](#environment-variables--configuration)
- [Concurrency Architecture & Worker Sharding](#concurrency-architecture--worker-sharding)
- [Container Infrastructure (`Dockerfile` & `cloud/entrypoint.sh`)](#container-infrastructure-dockerfile--cloudentrypointsh)
- [One-Time GCP Setup Guide](#one-time-gcp-setup-guide)
- [Executing Workflows via GCP Console](#executing-workflows-via-gcp-console)
  - [Workflow Parameter Reference](#workflow-parameter-reference)
  - [Execution Payloads](#execution-payloads)
- [Alternative: Running via Cloud Run Jobs](#alternative-running-via-cloud-run-jobs)
- [Live Log Inspection & Monitoring](#live-log-inspection--monitoring)
- [Storage Optimization & Cost Containment](#storage-optimization--cost-containment)

---

## Architecture & Processing Flow

The cloud subsystem isolates every subject onto an ephemeral compute instance, ensuring zero memory/CPU contention, predictable execution times, and automatic cost scaling.

```text
       ┌────────────────────────────────────────────────────────┐
       │              Google Cloud Console (UI)                 │
       │       Trigger: Cloud Workflow "run-mri-pipeline"       │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │               Google Cloud Batch Engine                │
       │     Job: mri-<pipeline>-<job_name>-<timestamp>         │
       │         parallelism = 10, taskCount = N                │
       └──────┬────────────────────┬────────────────────┬───────┘
              │                    │                    │
              ▼                    ▼                    ▼
     ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
     │ Task 0 (VM 1)   │  │ Task 1 (VM 2)   │  │ Task K (VM K)   │
     │ e2-custom-8-16G │  │ e2-custom-8-16G │  │ e2-custom-8-16G │
     │ 40 GB NVMe Disk │  │ 40 GB NVMe Disk │  │ 40 GB NVMe Disk │
     └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
              │                    │                    │
              ▼                    ▼                    ▼
     ┌──────────────────────────────────────────────────────────┐
     │              Google Cloud Storage (GCS)                  │
     │  - Download:  gs://<bucket>/inputs/<pipeline>/<subid>.zip│
     │  - Execute:   AFNI (create_timings -> preproc -> glm)    │
     │  - Upload:    gs://<bucket>/outputs/<pipeline>/<subid>/  │
     │  - Reports:   gs://<bucket>/reports/<pipeline>/          │
     └──────────────────────────────────────────────────────────┘
```

---

## GCS Bucket Organization

A single centralized GCS bucket (e.g., `gs://abend-lab-mri-analysis`) stores raw input archives, preprocessed derivatives, GLM models, and generated QC PDFs:

```text
gs://abend-lab-mri-analysis/
├── inputs/
│   ├── tim/
│   │   ├── sub-435.zip              # Raw BIDS archive (~1 GB) containing ses-1/{anat,func}
│   │   ├── sub-473.zip
│   │   └── ...
│   └── war/
│       ├── sub-AL01.zip
│       └── ...
├── outputs/
│   ├── tim/
│   │   ├── sub-435/
│   │   │   └── ses-1/
│   │   │       ├── timings/         # Synced from 00_create_timings.sh
│   │   │       ├── anat_warped/     # Synced from 01_preprocess_anat.sh (SSWarper)
│   │   │       ├── func_preproc/    # Synced from 02_preprocess_func.sh (pb00-pb04 purged)
│   │   │       └── glm/
│   │   │           ├── pain_by_rating/ # Stats, fitts, errts, and Chauffeur QC images
│   │   │           └── ...
│   │   ├── group_analysis/          # Group models synced from 04_run_group_analysis.sh
│   │   └── logs/                    # Step execution logs (<subject>_<step>.log)
│   └── war/
│       └── ...
└── reports/
    ├── tim/
    │   ├── sub-435/ses-1/*.pdf      # Consolidated APQC and GLM montage PDFs
    │   └── tim_consolidated_qc.pdf
    └── war/
```

> **Zip Layout Compatibility**:
> `cloud/gcs_helper.py` (`stage_in_subject_input`) automatically detects and unzips both common BIDS archive structures:
> 1. Top-level subject directory: `sub-435/ses-1/anat/...`
> 2. Top-level session directory: `ses-1/anat/...` (when the zip archive itself is named `sub-435.zip`).

---

## Environment Variables & Configuration

The container environment and Python controller respond to standard configuration variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PIPELINE` | `"tim"` | Task pipeline to execute (`"tim"` or `"war"`). |
| `GCS_BUCKET` | *required* | Target GCS bucket name or URI (e.g. `"abend-lab-mri-analysis"` or `"gs://..."`). |
| `SCRATCH_DIR` | `"/scratch"` | Local high-speed scratch mount (NVMe or internal SSD). |
| `EXPORT_QC_PDFS` | `"true"` | If `"true"`, automatically runs `export_results.py` to upload QC PDFs to GCS. |
| `KEEP_PB00_PB04` | `"0"` | Set to `"1"` to retain intermediate functional bricks; `"0"` automatically purges them. |
| `BATCH_TASK_INDEX` | *(injected)* | Index of current task in Cloud Batch array ($0 \dots N-1$). |
| `BATCH_TASK_COUNT` | *(injected)* | Total number of parallel tasks in Cloud Batch array. |
| `CLOUD_RUN_TASK_INDEX` | *(injected)* | Index of current task in Cloud Run Jobs array ($0 \dots N-1$). |
| `CLOUD_RUN_TASK_COUNT` | *(injected)* | Total number of parallel tasks in Cloud Run Jobs array. |

---

## Concurrency Architecture & Worker Sharding

Cloud Batch and Cloud Run Jobs inject task index and count variables into each container. `cloud/gcs_helper.py` provides deterministic, partition-complete subject sharding:

```python
def shard_subjects_for_cloud_task(subjects: List[str]) -> List[str]:
    """Returns the strided slice: subjects[task_index::task_count]."""
```

### Key Guarantees:
1. **Mathematical Completeness**: Every subject is assigned to exactly one worker. No subjects are duplicated; no subjects are omitted.
2. **Resource Isolation**: Each subject executes on an independent VM with dedicated 8 vCPUs and 16 GB RAM (`taskPack = 1`). Competing AFNI processes never contend for CPU or RAM.
3. **Queueing Beyond Parallelism**: If 50 subjects are submitted with `parallelism: 10`, Cloud Batch provisions 10 concurrent VMs and automatically schedules the next queued task as soon as any active VM completes, purging `/scratch` between runs.

---

## Container Infrastructure (`Dockerfile` & `cloud/entrypoint.sh`)

### Dockerfile Highlights
- Base image: Official AFNI distribution (`afni/afni_make_build:AFNI_24.0.00` or Debian-based AFNI build).
- Python environment: Python 3.8+ with `pandas`, `numpy`, `toml`, `rich`, `fpdf`, and headless Chrome for PDF conversion.
- System tools: `dcm2niix`, `google-cloud-sdk`, `zip`, `unzip`, `bc`.

### Entrypoint Workflow (`cloud/entrypoint.sh`)
1. Detects `BATCH_TASK_INDEX` or `CLOUD_RUN_TASK_INDEX`.
2. Validates `GCS_BUCKET` and creates `/scratch`.
3. Calls `shard_subjects_for_cloud_task` in `run_analysis.py`.
4. Executes the requested pipeline steps (`preprocess`, `glm`, `group_analysis`).
5. Executes `export_results.py` if `EXPORT_QC_PDFS="true"`.
6. Syncs final outputs and logs to GCS and cleans `/scratch`.

---

## One-Time GCP Setup Guide

Run these commands in **Google Cloud Shell** to prepare the GCP project:

```bash
# 1. Project variables
export PROJECT_ID=$(gcloud config get-value project)
export REGION="us-central1"
export BUCKET="abend-lab-mri-analysis"

# 2. Enable Required APIs
gcloud services enable \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    batch.googleapis.com \
    run.googleapis.com \
    workflows.googleapis.com \
    storage.googleapis.com

# 3. Create Storage Bucket
gcloud storage buckets create "gs://${BUCKET}" --location="${REGION}"

# 4. Create Artifact Registry Docker Repository
gcloud artifacts repositories create mri-analysis \
    --repository-format=docker \
    --location="${REGION}" \
    --description="AFNI fMRI analysis container images"

# 5. Build and Push Container Image via Cloud Build
gcloud builds submit \
    --config=cloud/cloudbuild.yaml \
    --substitutions="_REGION=${REGION},_REPO=mri-analysis" \
    .

# 6. Deploy Google Cloud Workflow
gcloud workflows deploy run-mri-pipeline \
    --source=cloud/workflow.yaml \
    --location="${REGION}"
```

---

## Executing Workflows via GCP Console

Once `run-mri-pipeline` is deployed, researchers can launch full parallel analyses directly from the browser:

1. Open **GCP Console** $\rightarrow$ **Workflows** $\rightarrow$ **`run-mri-pipeline`**.
2. Click **Execute**.
3. Paste a JSON payload into the **Input** editor and click **Execute**.

### Workflow Parameter Reference

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `job_name` | `string` | *(auto)* | Identifier tag for Cloud Batch and Cloud Logging (e.g. `"cohort1-preproc"`). |
| `pipeline` | `string` | `"tim"` | Task pipeline: `"tim"` or `"war"`. |
| `steps` | `list[str]` | `["preprocess", "glm"]` | Pipeline steps to execute (`create_timings`, `preprocess_anat`, `preprocess_func`, `glm`, `preprocess`, `all`, `group_analysis`). |
| `subjects` | `list[str]` | `[]` *(all)* | Array of subject IDs to process. |
| `analyses` | `list[str]` | `[]` | First-level GLM models (e.g. `["pain_by_rating"]` or `["all"]`). |
| `group_model` | `string` | `""` | Name of group model (required for `group_analysis`). |
| `use_spot_vms` | `bool` | `true` | `true` uses Spot VMs (~70% cost savings); `false` uses Standard On-Demand VMs. |
| `export_qc_pdfs` | `bool` | `true` | Automatically compiles and uploads QC PDFs to `reports/`. |
| `parallelism` | `int` | `10` | Maximum number of subject VMs executing concurrently. |

---

### Execution Payloads

#### Example 1: Parallel Preprocessing & GLM on 10 TIM Subjects (Spot VMs)

```json
{
  "job_name": "tim-cohort1-full",
  "pipeline": "tim",
  "steps": ["preprocess", "glm"],
  "subjects": [
    "sub-435", "sub-473", "sub-489", "sub-499", "sub-500",
    "sub-502", "sub-503", "sub-504", "sub-505", "sub-506"
  ],
  "analyses": ["all"],
  "use_spot_vms": true,
  "export_qc_pdfs": true,
  "parallelism": 10
}
```

#### Example 2: First-Level GLM for Specific Models on WAR Subjects

```json
{
  "job_name": "war-glm-block-image",
  "pipeline": "war",
  "steps": ["glm"],
  "subjects": ["sub-AL01", "sub-AL02", "sub-AL03"],
  "analyses": ["by_block", "by_image"],
  "use_spot_vms": true,
  "export_qc_pdfs": true
}
```

#### Example 3: Group-Level Analysis (`3dLMEr` or `3dttest++`)

```json
{
  "job_name": "group-pain-by-rating",
  "pipeline": "tim",
  "steps": ["group_analysis"],
  "analyses": ["pain_by_rating"],
  "group_model": "pain_by_rating",
  "use_spot_vms": false
}
```

---

## Alternative: Running via Cloud Run Jobs

The same Docker container can be launched as a serverless Cloud Run Job:

```bash
gcloud run jobs create mri-tim-runner \
    --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/mri-analysis/afni-pipeline:latest" \
    --region="${REGION}" \
    --cpu=8 \
    --memory=32Gi \
    --task-timeout=3600s \
    --set-env-vars="PIPELINE=tim,GCS_BUCKET=${BUCKET},EXPORT_QC_PDFS=true"
```

In the **Cloud Run Jobs** console, select **Execute with overrides**, set **Tasks = 10**, and supply arguments:
`--step preprocess glm --subject sub-435 sub-473 sub-489 sub-499 sub-500 sub-502 sub-503 sub-504 sub-505 sub-506`

---

## Live Log Inspection & Monitoring

1. **GCP Console UI**:
   - Go to **Batch** $\rightarrow$ **Job list** $\rightarrow$ Click Job $\rightarrow$ **Logs** tab.
2. **Command Line (Cloud Logging)**:
   ```bash
   gcloud logging read 'logName="projects/neuroscience-lab/logs/batch_task_logs" AND labels.job_uid=~"mri-tim-"' \
       --project=neuroscience-lab \
       --limit=50 \
       --format="value(textPayload)"
   ```
3. **Persistent Step Logs in GCS**:
   - Every subject run uploads detailed stdout/stderr logs to:
     `gs://abend-lab-mri-analysis/outputs/<pipeline>/logs/<subject>_<step>.log`

---

## Storage Optimization & Cost Containment

1. **Spot VMs (`use_spot_vms: true`)**:
   - Reduces Compute Engine VM costs by ~60–80%.
2. **Intermediate Brick Purging (`KEEP_PB00_PB04=0`)**:
   - Deleting `pb00` through `pb04` reduces output storage from ~30 GB to ~5 GB per subject, saving significant long-term GCS storage costs.
3. **Scratch Auto-Cleanup (`cleanup_scratch = true`)**:
   - Local ephemeral disks are completely wiped between runs, avoiding disk-full crashes on high-throughput VM workers.
