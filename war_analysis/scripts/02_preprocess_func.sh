#!/bin/bash

# --- Script: 02_preprocess_func.sh ---
# Description: Runs functional preprocessing using afni_proc.py, creating analysis-ready datasets.

set -e # Exit immediately if a command exits with a non-zero status.

# Get the directory where the script is located
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Source the color utility script
source "${SCRIPT_DIR}/utils_colors.sh"

# Default values
SUBJECT=""
SESSION="1"
INPUT_DIR=""
OUTPUT_DIR=""

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --subject) SUBJECT="$2"; shift 2;;
        --session) SESSION="$2"; shift 2;;
        --input) INPUT_DIR="$2"; shift 2;;
        --output) OUTPUT_DIR="$2"; shift 2;;
        *) log_error "Unknown option: $1"; exit 1;;
    esac
done

# Validate required arguments
if [ -z "$SUBJECT" ] || [ -z "$SESSION" ] || [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ]; then
    log_error "Usage: $0 --subject <ID> --session <N> --input <dir> --output <dir>"
    exit 1
fi

SESSION_PREFIX="ses-${SESSION}"
ANAT_WARPED_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/anat_warped"
FUNC_PREPROC_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func_preproc"

# Find the MNI template
MNI_TEMPLATE=$(find "${INPUT_DIR}/.." -name "MNI152_2009_template.nii.gz" | head -n 1)
if [ -z "$MNI_TEMPLATE" ]; then
    log_error "MNI152_2009_template.nii.gz not found."
    exit 1
fi

print_header "Starting Functional Preprocessing for ${SUBJECT}, ${SESSION_PREFIX}"

# Clean up previous output directory
if [ -d "$FUNC_PREPROC_DIR" ]; then
    log_warn "Found existing func_preproc folder, deleting it: ${FUNC_PREPROC_DIR}"
    rm -rf "$FUNC_PREPROC_DIR"
fi

# Create the output directory and cd into it
mkdir -p "$FUNC_PREPROC_DIR"
cd "$FUNC_PREPROC_DIR"

log_info "Running afni_proc.py..."
afni_proc.py \
    -subj_id "${SUBJECT}_preproc" \
    -dsets_me_run \
        "${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/${SUBJECT}_${SESSION_PREFIX}_task-war_run-1_echo-1_bold.nii.gz" \
        "${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/${SUBJECT}_${SESSION_PREFIX}_task-war_run-1_echo-2_bold.nii.gz" \
        "${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/${SUBJECT}_${SESSION_PREFIX}_task-war_run-1_echo-3_bold.nii.gz" \
    -dsets_me_run \
        "${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/${SUBJECT}_${SESSION_PREFIX}_task-war_run-2_echo-1_bold.nii.gz" \
        "${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/${SUBJECT}_${SESSION_PREFIX}_task-war_run-2_echo-2_bold.nii.gz" \
        "${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/${SUBJECT}_${SESSION_PREFIX}_task-war_run-2_echo-3_bold.nii.gz" \
    -echo_times 13.6 25.96 38.3 \
    -copy_anat "${ANAT_WARPED_DIR}/anatSS.${SUBJECT}.nii" \
    -anat_has_skull no \
    -anat_follower anat_w_skull anat "${ANAT_WARPED_DIR}/anatU.${SUBJECT}.nii" \
    -blocks tshift align tlrc volreg mask combine blur scale regress \
    -html_review_style pythonic \
    -align_unifize_epi local \
    -align_opts_aea -cost lpc+ZZ -giant_move -check_flip \
    -volreg_align_to MIN_OUTLIER \
    -volreg_align_e2a \
    -volreg_tlrc_warp \
    -volreg_compute_tsnr yes \
    -mask_epi_anat yes \
    -mask_segment_anat yes \
    -combine_method OC \
    -blur_size 4 \
    -tlrc_base "$MNI_TEMPLATE" \
    -tlrc_NL_warp \
    -tlrc_NL_warped_dsets \
        "${ANAT_WARPED_DIR}/anatQQ.${SUBJECT}.nii" \
        "${ANAT_WARPED_DIR}/anatQQ.${SUBJECT}.aff12.1D" \
        "${ANAT_WARPED_DIR}/anatQQ.${SUBJECT}_WARP.nii" \
    -regress_motion_per_run \
    -regress_censor_motion 0.5 \
    -regress_censor_outliers 0.05 \
    -execute

log_success "Functional Preprocessing for ${SUBJECT} Complete"
