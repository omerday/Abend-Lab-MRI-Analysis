#!/bin/bash

# --- Script: 02_preprocess_func.sh ---
# Description: Runs functional preprocessing using afni_proc.py.
# Date: 2025-09-16

set -e # Exit immediately if a command exits with a non-zero status.

# Default values
SUBJECT=""
SESSION="1"
INPUT_DIR=""
OUTPUT_DIR=""
RUNS=5 # Default number of runs

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --subject)
            SUBJECT="$2"
            shift 2
            ;; 
        --session)
            SESSION="$2"
            shift 2
            ;; 
        --input)
            INPUT_DIR="$2"
            shift 2
            ;; 
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;; 
        --runs)
            RUNS="$2"
            shift 2
            ;; 
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;; 
    esac
done

# Validate required arguments
if [ -z "$SUBJECT" ] || [ -z "$SESSION" ] || [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ]; then
    echo "Usage: $0 --subject <ID> --session <N> --input <dir> --output <dir> [--runs <N>]" >&2
    exit 1
fi

SESSION_PREFIX="ses-${SESSION}"
ANAT_WARPED_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/anat_warped"
FUNC_PREPROC_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/preproc"

echo "--- Starting Functional Preprocessing for ${SUBJECT}, ${SESSION_PREFIX} ---"

# Clean up previous output directory
if [ -d "$FUNC_PREPROC_DIR" ]; then
    echo "Found existing preproc folder, deleting it: ${FUNC_PREPROC_DIR}"
    rm -rf "$FUNC_PREPROC_DIR"
fi

# Create the output directory and cd into it
mkdir -p "$FUNC_PREPROC_DIR"
cd "$FUNC_PREPROC_DIR"

# Construct -dsets_me_run argument
DSETS=""
for i in $(seq 1 $RUNS); do
    DSETS+="-dsets_me_run \
        ${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/${SUBJECT}_${SESSION_PREFIX}_task-tim_run-${i}_echo-1_bold.nii.gz \
        ${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/${SUBJECT}_${SESSION_PREFIX}_task-tim_run-${i}_echo-2_bold.nii.gz \
        ${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/${SUBJECT}_${SESSION_PREFIX}_task-tim_run-${i}_echo-3_bold.nii.gz "
done

afni_proc.py \
    -subj_id "${SUBJECT}_preproc" \
    ${DSETS} \
    -echo_times 13.6 25.96 38.3 \
    -copy_anat "${ANAT_WARPED_DIR}/anatSS.${SUBJECT}.nii" \
    -anat_has_skull no \
    -anat_follower anat_w_skull anat "${ANAT_WARPED_DIR}/anatU.${SUBJECT}.nii" \
    -blocks tshift align tlrc volreg mask combine blur scale regress\
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
    -tlrc_base MNI152_2009_template.nii.gz \
    -tlrc_NL_warp \
    -tlrc_NL_warped_dsets \
        "${ANAT_WARPED_DIR}/anatQQ.${SUBJECT}.nii" \
        "${ANAT_WARPED_DIR}/anatQQ.${SUBJECT}.aff12.1D" \
        "${ANAT_WARPED_DIR}/anatQQ.${SUBJECT}_WARP.nii" \
    -html_review_style pythonic \
    -execute

echo "--- Functional Preprocessing for ${SUBJECT} Complete ---"
