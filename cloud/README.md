# Google Cloud Platform (GCP) Execution Guide for TIM & WAR fMRI Pipelines

This directory contains everything needed to deploy and run the Abend Lab's `tim_analysis` and `war_analysis` fMRI pipelines on **Google Cloud Platform (GCP)** using **Google Cloud Storage (GCS)**, **Google Cloud Batch** (or **Cloud Run Jobs**), and **Google Cloud Workflows** (so jobs can be triggered directly from the GCP Console browser UI without any local CLI).

---

## 1. GCS Bucket Layout

Create a single GCS bucket (e.g., `gs://abend-lab-mri-analysis`) organized as follows:

```text
gs://abend-lab-mri-analysis/
├── inputs/
│   ├── tim/
│   │   ├── sub-435.zip          # ~1 GB zip of sub-435/ses-1/{anat,func,fmap,...}
│   │   ├── sub-473.zip
│   │   └── ...
│   └── war/
│       ├── sub-MD18.zip
│       └── ...
├── outputs/
│   ├── tim/
│   │   ├── sub-435/
│   │   │   └── ses-1/
│   │   │       ├── timings/                 # Synced from 00_create_timings.sh
│   │   │       ├── anat_warped/             # Synced from 01_preprocess_anat.sh
│   │   │       ├── func_preproc/            # Synced from 02_preprocess_func.sh (pb00-pb04 auto-cleaned)
│   │   │       └── glm/
│   │   │           ├── sanity_check/        # Synced from 03_run_glm.sh (includes stats, fitts, errts, QC)
│   │   │           ├── pain_by_rating/
│   │   │           └── ...
│   │   ├── group_analysis/
│   │   │   └── <analysis>/<group_model>/    # Synced from 04_run_group_analysis.sh
│   │   └── logs/                            # Per-subject step execution logs
│   └── war/
└── reports/
    ├── tim/
    │   ├── sub-435/ses-1/*.pdf              # Exported QC & GLM PDFs
    │   └── consolidated_report.pdf
    └── war/
```

> **Note on Input Zip Structure**:
> `cloud/gcs_helper.py` automatically handles both zip layouts:
> 1. Top-level subject folder: `sub-435/ses-1/anat/...` and `sub-435/ses-1/func/...`
> 2. Top-level session folder: `ses-1/anat/...` and `ses-1/func/...` (when the zip itself is named `sub-435.zip`).

---

## 2. One-Time GCP Project Setup (Run in Google Cloud Shell)

You can run these setup commands directly inside the browser-based **Google Cloud Shell** in the GCP Console:

```bash
# 1. Set your Project ID, Region, and Bucket Name
export PROJECT_ID=$(gcloud config get-value project)
export REGION="me-west1"   # or "us-central1"
export BUCKET="abend-lab-mri-analysis"

# 2. Enable Required GCP APIs
gcloud services enable \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    batch.googleapis.com \
    run.googleapis.com \
    workflows.googleapis.com \
    storage.googleapis.com

# 3. Create the GCS Bucket
gcloud storage buckets create "gs://${BUCKET}" --location="${REGION}"

# 4. Create the Artifact Registry Docker Repository
gcloud artifacts repositories create mri-analysis \
    --repository-format=docker \
    --location="${REGION}" \
    --description="AFNI fMRI analysis container images"

# 5. Build and Push the Docker Image using Cloud Build
gcloud builds submit \
    --config=cloud/cloudbuild.yaml \
    --substitutions="_REGION=${REGION},_REPO=mri-analysis" \
    .

# 6. Deploy the Cloud Workflow (for 1-Click Browser Execution)
gcloud workflows deploy run-mri-pipeline \
    --source=cloud/workflow.yaml \
    --location="${REGION}"
```

---

## 3. Running Analyses Directly from the GCP Console UI

Once `run-mri-pipeline` is deployed in **Cloud Workflows**, you never need a terminal to run analyses:

1. Open the **Google Cloud Console** $\rightarrow$ **Workflows** $\rightarrow$ **`run-mri-pipeline`**.
2. Click **Execute**.
3. Paste one of the JSON payloads below into the **Input** box and click **Execute**.

### Supported Workflow Input Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| **`job_name`** | `string` | *(auto-generated)* | Optional custom name tag for easy identification in Cloud Batch & Cloud Logging (e.g., `"cohort1-preproc"`). Produces job IDs like `mri-tim-cohort1-preproc-20261017t140000`. If omitted, auto-generates from the step and subject(s) (e.g., `mri-tim-preprocess-sub-435-20261017t140000`). |
| **`pipeline`** | `string` | `"tim"` | Which task pipeline to run: `"tim"` or `"war"`. |
| **`steps`** | `list[str]` | `["preprocess", "glm"]` | Steps to execute in sequence: `"create_timings"`, `"preprocess_anat"`, `"preprocess_func"`, `"preprocess"`, `"glm"`, `"all"`, or `"group_analysis"`. |
| **`subjects`** | `list[str]` | `[]` *(all subjects)* | List of subject IDs (e.g., `["sub-435", "sub-473"]`). Each subject runs on its own isolated VM. |
| **`analyses`** | `list[str]` | `[]` | First-level GLM model name(s), e.g. `["all"]` or `["sanity_check", "pain_by_rating"]`. |
| **`group_model`** | `string` | `""` | Group analysis model name (required when `steps` is `["group_analysis"]`). |
| **`session`** | `int`/`str` | `""` *(all sessions)* | Optional session number override (e.g., `1`). |
| **`use_spot_vms`** | `bool` | `true` | `true` = use **Spot VMs** (~70% cheaper, `provisioningModel: "SPOT"`). `false` = use **Standard On-Demand VMs** (`provisioningModel: "STANDARD"`, guaranteed no preemption). |
| **`export_qc_pdfs`** | `bool` | `true` | Automatically run `export_results.py` after pipeline steps to upload QC & GLM PDFs to `gs://<bucket>/reports/<pipeline>/`. |
| **`parallelism`** | `int` | `10` | Maximum number of subject VMs to run concurrently. |
| **`machine_type`** | `string` | `"e2-custom-8-16384"` | Compute Engine machine type per subject VM (8 vCPUs, 16 GB RAM). |

---

### Example A: Run `preprocess` + `glm` on 10 TIM Subjects in Parallel
*(Cloud Equivalent of `python tim_analysis/run_analysis.py --step preprocess glm` on 10 subjects)*

```json
{
  "job_name": "cohort1-preproc-glm",
  "pipeline": "tim",
  "steps": ["preprocess", "glm"],
  "subjects": [
    "sub-435", "sub-473", "sub-489", "sub-499", "sub-500",
    "sub-502", "sub-503", "sub-504", "sub-505", "sub-506"
  ],
  "analyses": ["all"],
  "use_spot_vms": true,
  "export_qc_pdfs": true
}
```
**What happens automatically:**
- Cloud Workflows launches a **Cloud Batch** job named `mri-tim-cohort1-preproc-glm-<timestamp>` with **10 parallel tasks** (`taskCount = 10`).
- Each task (`BATCH_TASK_INDEX = 0..9`) runs on its own dedicated `e2-custom-8-16384` VM (8 vCPUs, 16 GB RAM, 40 GB `pd-balanced` disk), claims 1 subject, downloads `gs://abend-lab-mri-analysis/inputs/tim/sub-XXX.zip` onto its local `/scratch`, runs `create_timings` $\rightarrow$ `preprocess_anat` $\rightarrow$ `preprocess_func` (automatically deleting intermediate `pb00`–`pb04` bricks while keeping `pb05`, `fitts`, and `errts`) $\rightarrow$ `glm` across all TIM models, syncs each step's output to `gs://abend-lab-mri-analysis/outputs/tim/sub-XXX/`, exports QC PDFs to `gs://abend-lab-mri-analysis/reports/tim/`, and shuts down immediately when finished.

### Example B: Run Specific GLM Model(s) on Already-Preprocessed WAR Subjects

```json
{
  "job_name": "war-block-image-glm",
  "pipeline": "war",
  "steps": ["glm"],
  "subjects": ["sub-MD21", "sub-MD23", "sub-MD24", "sub-MD25"],
  "analyses": ["by_block", "by_image"],
  "use_spot_vms": true,
  "export_qc_pdfs": true
}
```
*(Since `preprocess` is already in GCS, each container skips raw input zip download, stages in `func_preproc/` and `timings/` from GCS, runs the requested GLMs, and uploads the new GLM results).*

### Example C: Run Group Analysis (`3dttest++` or `3dLMEr`)

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
*(Runs a single worker that selectively stages only `mask_epi_anat.*` and `stats.*` files from GCS for all group subjects, executes `04_run_group_analysis.sh`, and uploads results to `gs://.../outputs/tim/group_analysis/pain_by_rating/pain_by_rating/`).*

---

## 4. Concurrency Architecture & Resource Isolation

- **Dedicated VM Per Concurrent Subject**: Each task in a Cloud Batch job requests 8 vCPUs (`cpuMilli: 8000`), 16 GB RAM, and 40 GB `pd-balanced` disk on an `e2-custom-8-16384` VM (`taskPack = 1`). Concurrent subjects **never share CPU, RAM, or disk**.
- **Automatic Task Sharding (`cloud/gcs_helper.py`)**: Cloud Batch injects `BATCH_TASK_INDEX` (`0..N-1`) and `BATCH_TASK_COUNT` (`N`) into each container. `shard_subjects_for_cloud_task()` assigns each task its dedicated subject slice `subjects[idx::total]`.
- **Queueing Beyond `parallelism`**: If you pass 49 subjects with `parallelism: 10`, Cloud Batch runs 10 VMs concurrently and automatically starts the next queued subject as soon as any VM finishes, cleaning `/scratch` between subjects.

---

## 5. Viewing Live Logs & Monitoring Jobs

1. **In the GCP Console UI**:
   - Navigate to **Batch** $\rightarrow$ **Job list**, click your job (e.g. `mri-tim-cohort1-preproc-glm-...`), and open the **Logs** tab.
2. **Via `gcloud logging read` CLI (filtering out agent heartbeats)**:
   ```bash
   gcloud logging read 'logName="projects/neuroscience-lab/logs/batch_task_logs" AND labels.job_uid=~"mri-tim-"' \
       --project=neuroscience-lab \
       --limit=50 \
       --format="value(textPayload)"
   ```
3. **Permanent Step Log Files in GCS**:
   - At the end of every step, the full step log is also uploaded to `gs://abend-lab-mri-analysis/outputs/<pipeline>/logs/<subject>_<step>.log`.

---

## 6. Alternative: Running via Cloud Run Jobs UI

Because `cloud/entrypoint.sh` and `cloud/gcs_helper.py` read both `BATCH_TASK_INDEX` and `CLOUD_RUN_TASK_INDEX`, the exact same container image also works as a **Cloud Run Job**:

```bash
gcloud run jobs create mri-tim-runner \
    --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/mri-analysis/afni-pipeline:latest" \
    --region="${REGION}" \
    --cpu=8 \
    --memory=32Gi \
    --task-timeout=3600s \
    --set-env-vars="PIPELINE=tim,GCS_BUCKET=${BUCKET},EXPORT_QC_PDFS=true"
```
In the **Cloud Run Jobs** Console UI, click **Execute with overrides**, set **Number of tasks = 10**, and set container arguments to:
`--step preprocess glm --subject sub-435 sub-473 sub-489 sub-499 sub-500 sub-502 sub-503 sub-504 sub-505 sub-506`
