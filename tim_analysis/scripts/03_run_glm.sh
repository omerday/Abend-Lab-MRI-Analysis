#!/bin/bash

# --- Script: 03_run_glm.sh ---
# Description: Runs a specific GLM analysis on preprocessed data.
# Date: 2025-09-16

set -e # Exit immediately if a command exits with a non-zero status.

# Default values
SUBJECT=""
SESSION="1"
INPUT_DIR=""
OUTPUT_DIR=""
ANALYSIS_NAME=""
RUNS=5

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
        --analysis)
            ANALYSIS_NAME="$2"
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
if [ -z "$SUBJECT" ] || [ -z "$SESSION" ] || [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$ANALYSIS_NAME" ]; then
    echo "Usage: $0 --subject <ID> --session <N> --input <dir> --output <dir> --analysis <name> [--runs <N>]" >&2
    exit 1
fi

SESSION_PREFIX="ses-${SESSION}"
PREPROC_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func/preproc/${SUBJECT}_preproc.results"
GLM_OUTPUT_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/${ANALYSIS_NAME}"
TIMING_DIR="${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func"

# --- Load Model Configuration ---
# This is a simple parser for the TOML file. A more robust solution might use a proper tool.
MODEL_CONFIG=$(awk -v model="$ANALYSIS_NAME" '/^[\[]/{in_model=0} $0=="["model"]"{in_model=1} in_model' "analysis_configs/analysis_models.toml")

STIM_FILES_RAW=$(echo "$MODEL_CONFIG" | grep 'stim_files' | sed 's/stim_files = \[\(.*\)\]/\1/' | tr -d '\"' | tr -d ' ')
STIM_LABELS_RAW=$(echo "$MODEL_CONFIG" | grep 'stim_labels' | sed 's/stim_labels = \[\(.*\)\]/\1/' | tr -d '\"' | tr -d ' ')
BASIS=$(echo "$MODEL_CONFIG" | grep 'basis' | sed 's/basis = \"\(.*\)\"/\1/')

IFS=',' read -r -a STIM_FILES <<< "$STIM_FILES_RAW"
IFS=',' read -r -a STIM_LABELS <<< "$STIM_LABELS_RAW"

REGRESS_STIM_TIMES_ARGS=""
for file in "${STIM_FILES[@]}"; do
    REGRESS_STIM_TIMES_ARGS+="-regress_stim_times ${TIMING_DIR}/${file} "
done

REGRESS_STIM_LABELS_ARGS="-regress_stim_labels ${STIM_LABELS[*]}"

GLT_ARGS=""
# A simple loop to parse GLT syms and labels
while read -r line; do
    if [[ $line == *"sym ="* ]]; then
        sym=$(echo "$line" | sed -e 's/.*sym = \"\(.*\)\".*/\1/)
    elif [[ $line == *"label ="* ]]; then
        label=$(echo "$line" | sed -e 's/.*label = \"\(.*\)\".*/\1/)
        GLT_ARGS+="-gltsym 'SYM: ${sym}' -glt_label ${#GLT_ARGS[@]+1} ${label} "
    fi
done <<< "$(echo "$MODEL_CONFIG" | grep -A 2 'glt')"

echo "--- Starting GLM Analysis (${ANALYSIS_NAME}) for ${SUBJECT}, ${SESSION_PREFIX} ---"

# Clean up previous output directory
if [ -d "$GLM_OUTPUT_DIR" ]; then
    echo "Found existing GLM folder, deleting it: ${GLM_OUTPUT_DIR}"
    rm -rf "$GLM_OUTPUT_DIR"
fi

# Create the output directory and cd into it
mkdir -p "$GLM_OUTPUT_DIR"
cd "$GLM_OUTPUT_DIR"

# Run afni_proc.py for the GLM
# Note: We are providing the preprocessed datasets directly via -dsets
afni_proc.py \
    -subj_id "${SUBJECT}_${ANALYSIS_NAME}" \
    -dsets ${PREPROC_DIR}/pb05.${SUBJECT}_preproc.r*.scale+tlrc.HEAD \
    -blocks regress \
    ${REGRESS_STIM_TIMES_ARGS} \
    ${REGRESS_STIM_LABELS_ARGS} \
    -regress_stim_types AM2 \
    -regress_basis "$BASIS" \
    ${GLT_ARGS} \
    -regress_opts_3dD -jobs 8 \
    -regress_motion_file ${PREPROC_DIR}/dfile_rall.1D \
    -regress_motion_per_run \
    -regress_censor_motion 0.5 \
    -regress_censor_outliers 0.05 \
    -regress_reml_exec \
    -regress_no_mask \
    -regress_compute_fitts \
    -regress_make_ideal_sum sum_ideal.1D \
    -regress_run_clustsim no \
    -remove_preproc_files \
    -html_review_style pythonic \
    -execute

echo "--- GLM Analysis for ${SUBJECT} Complete ---"
