#!/bin/bash
# ==============================================================================
# Cloud Container Entrypoint for Abend Lab fMRI Analysis (TIM & WAR)
#
# Supports execution on both Google Cloud Batch and Google Cloud Run Jobs, as
# well as local Docker testing.
#
# Environment Variables (or CLI arguments):
#   PIPELINE          : "tim" (default) or "war"
#   GCS_BUCKET        : Optional bucket name (e.g., "abend-lab-mri-analysis").
#                       If set, automatically configures:
#                         MRI_INPUT_DIR="gs://${GCS_BUCKET}/inputs/${PIPELINE}"
#                         MRI_OUTPUT_DIR="gs://${GCS_BUCKET}/outputs/${PIPELINE}"
#                         MRI_REPORTS_DIR="gs://${GCS_BUCKET}/reports/${PIPELINE}"
#   MRI_INPUT_DIR     : Explicit input path or gs:// URI
#   MRI_OUTPUT_DIR    : Explicit output path or gs:// URI
#   MRI_REPORTS_DIR   : Explicit PDF report destination path or gs:// URI
#   SCRATCH_DIR       : Local scratch path (default: /scratch if mounted, else /tmp/afni_scratch)
#   EXPORT_QC_PDFS    : "true" (default) or "false" - whether to run export_results.py after steps
#   OMP_NUM_THREADS   : Number of OpenMP threads for AFNI (sswarper2, 3dQwarp, 3dREMLfit, etc.)
# ==============================================================================

set -euo pipefail

# Environment & Dependencies
export PYTHONPATH="/opt/pydeps:/opt/user_pip_packages/lib/python3.6/site-packages:/app:${PYTHONPATH:-}"
export CLOUDSDK_CONFIG="${CLOUDSDK_CONFIG:-/tmp/gcloud_config}"
mkdir -p "$CLOUDSDK_CONFIG"

PIPELINE="${PIPELINE:-tim}"
PIPELINE="$(echo "$PIPELINE" | tr '[:upper:]' '[:lower:]')"

if [ "$PIPELINE" = "war" ] || [ "$PIPELINE" = "war_analysis" ]; then
    PIPELINE="war"
    PIPELINE_DIR="/app/war_analysis"
elif [ "$PIPELINE" = "tim" ] || [ "$PIPELINE" = "tim_analysis" ]; then
    PIPELINE="tim"
    PIPELINE_DIR="/app/tim_analysis"
else
    echo "[ERROR] Unknown PIPELINE='${PIPELINE}'. Must be 'tim' or 'war'." >&2
    exit 1
fi

# Auto-configure GCS URIs if GCS_BUCKET is provided
if [ -n "${GCS_BUCKET:-}" ]; then
    GCS_BUCKET="${GCS_BUCKET#gs://}"
    GCS_BUCKET="${GCS_BUCKET%/}"
    export MRI_INPUT_DIR="${MRI_INPUT_DIR:-gs://${GCS_BUCKET}/inputs/${PIPELINE}}"
    export MRI_OUTPUT_DIR="${MRI_OUTPUT_DIR:-gs://${GCS_BUCKET}/outputs/${PIPELINE}}"
    export MRI_REPORTS_DIR="${MRI_REPORTS_DIR:-gs://${GCS_BUCKET}/reports/${PIPELINE}}"
fi

# Determine fast scratch directory (/mnt/disks/scratch on Cloud Batch SSD, or /scratch, or /tmp/afni_scratch)
if [ -z "${SCRATCH_DIR:-}" ]; then
    if [ -d "/mnt/disks/scratch" ]; then
        export SCRATCH_DIR="/mnt/disks/scratch/afni_scratch"
    elif [ -d "/scratch" ]; then
        export SCRATCH_DIR="/scratch/afni_scratch"
    else
        export SCRATCH_DIR="/tmp/afni_scratch"
    fi
fi
mkdir -p "$SCRATCH_DIR"

# Default OpenMP threads to available vCPUs
if [ -z "${OMP_NUM_THREADS:-}" ]; then
    export OMP_NUM_THREADS="$(nproc 2>/dev/null || echo 8)"
fi

# Determine Task Index and Count for logging
TASK_INDEX="${BATCH_TASK_INDEX:-${CLOUD_RUN_TASK_INDEX:-local}}"
TASK_COUNT="${BATCH_TASK_COUNT:-${CLOUD_RUN_TASK_COUNT:-1}}"

# Normalize EXPORT_QC_PDFS (defaults to true as documented)
EXPORT_QC_PDFS="${EXPORT_QC_PDFS:-true}"
EXPORT_QC_PDFS="$(echo "$EXPORT_QC_PDFS" | tr '[:upper:]' '[:lower:]')"

echo "============================================================"
echo "  Abend Lab fMRI Cloud Runner"
echo "  Pipeline        : ${PIPELINE} (${PIPELINE_DIR})"
echo "  Input Dir       : ${MRI_INPUT_DIR:-(from main_config.toml)}"
echo "  Output Dir      : ${MRI_OUTPUT_DIR:-(from main_config.toml)}"
echo "  Reports Dir     : ${MRI_REPORTS_DIR:-(from main_config.toml)}"
echo "  Scratch Dir     : ${SCRATCH_DIR}"
echo "  OMP_NUM_THREADS : ${OMP_NUM_THREADS}"
echo "  Task Shard      : Index=${TASK_INDEX} / Count=${TASK_COUNT}"
echo "  Export QC PDFs  : ${EXPORT_QC_PDFS}"
echo "  Arguments       : $*"
echo "============================================================"

cd "$PIPELINE_DIR"

# Track Xvfb process PID for clean lifecycle management
XVFB_PID=""
cleanup() {
    local exit_code=$?
    if [ -n "$XVFB_PID" ] && kill -0 "$XVFB_PID" >/dev/null 2>&1; then
        kill "$XVFB_PID" >/dev/null 2>&1 || true
    fi
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

# Start Xvfb in the background if not already running (needed by @chauffeur_afni and wkhtmltopdf)
if command -v Xvfb >/dev/null 2>&1 && [ -z "${DISPLAY:-}" ]; then
    XVFB_DISPLAY=":99"
    Xvfb "$XVFB_DISPLAY" -screen 0 1600x1200x24 -nolisten tcp >/dev/null 2>&1 &
    XVFB_PID=$!
    export DISPLAY="$XVFB_DISPLAY"
fi

# If first arg is a custom command (e.g. "export_results.py" or "concatenate_reports.py" or "bash"), run it directly
if [ "$#" -gt 0 ]; then
    case "$1" in
        export_results.py|concatenate_reports.py)
            SCRIPT="$1"
            shift
            python3 "$SCRIPT" "$@"
            exit 0
            ;;
        bash|sh|python|python3)
            # For interactive/subshell, stop Xvfb before exec if we spawned it
            if [ -n "$XVFB_PID" ] && kill -0 "$XVFB_PID" >/dev/null 2>&1; then
                kill "$XVFB_PID" >/dev/null 2>&1 || true
                XVFB_PID=""
            fi
            exec "$@"
            ;;
    esac
fi

# Otherwise, pass all arguments to run_analysis.py
python3 run_analysis.py --scratch_dir "$SCRATCH_DIR" "$@"

# Run export_results.py if EXPORT_QC_PDFS is true and MRI_REPORTS_DIR is set
if [ "$EXPORT_QC_PDFS" = "true" ] && [ -n "${MRI_REPORTS_DIR:-}" ]; then
    echo "--- Exporting QC PDFs to ${MRI_REPORTS_DIR} ---"
    python3 export_results.py --output_dir "${MRI_OUTPUT_DIR:-}" --dropbox_dir "$MRI_REPORTS_DIR" || true
fi
