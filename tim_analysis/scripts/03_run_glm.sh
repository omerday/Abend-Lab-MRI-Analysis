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
GLT_LABELS=()
while read -r line; do
    if [[ $line == *"sym ="* ]]; then
        sym=$(echo "$line" | sed -e 's/.*sym = \"\(.*\)\".*/\1/)
    elif [[ $line == *"label ="* ]]; then
        label=$(echo "$line" | sed -e 's/.*label = \"\(.*\)\".*/\1/)
        GLT_ARGS+="-gltsym 'SYM: ${sym}' -glt_label ${#GLT_ARGS[@]+1} ${label} "
        GLT_LABELS+=("$label")
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

echo "--- Masking stats and generating images with @chauffeur_afni ---"

RESULTS_DIR="${SUBJECT}_${ANALYSIS_NAME}.results"
ANAT_FINAL="${PREPROC_DIR}/anat_final.${SUBJECT}_preproc+tlrc.HEAD"

# Mask the stats output with the EPI mask from preprocessing
3dcalc \
    -a "${RESULTS_DIR}/stats.${SUBJECT}_${ANALYSIS_NAME}+tlrc.HEAD" \
    -b "${PREPROC_DIR}/mask_epi_anat.${SUBJECT}_preproc+tlrc.HEAD" \
    -expr 'a*b' \
    -prefix "${RESULTS_DIR}/masked_stats.${SUBJECT}_${ANALYSIS_NAME}"

CHAUFFEUR_DIR="${RESULTS_DIR}/chauffeur_images"
mkdir -p "$CHAUFFEUR_DIR"

# Function to run chauffeur for a given sub-brick label
run_chauffeur() {
    local brick_label=$1
    local output_prefix=$2
    echo "Generating image for: ${brick_label}"
    @chauffeur_afni \
        -ulay "${ANAT_FINAL}" \
        -ulay_range 0% 130% \
        -olay "${RESULTS_DIR}/masked_stats.${SUBJECT}_${ANALYSIS_NAME}+tlrc.HEAD" \
        -box_focus_slices AMASK_FOCUS_ULAY \
        -func_range 3 \
        -cbar Reds_and_Blues_Inv \
        -thr_olay_p2stat 0.05 \
        -thr_olay_pside bisided \
        -olay_alpha Yes \
        -olay_boxed Yes \
        -set_subbricks -1 "${brick_label}_Coef" "${brick_label}_Tstat" \
        -clusterize "-NN 2 -clust_nvox 40" \
        -set_dicom_xyz -20 -8 -16 \
        -delta_slices 6 15 10 \
        -opacity 5 \
        -prefix "${output_prefix}" \
        -set_xhairs OFF \
        -montx 3 -monty 3 \
        -label_mode 1 -label_size 4
}

# Check if we have explicit GLTs. If so, loop through them.
if [ ${#GLT_LABELS[@]} -gt 0 ]; then
    for label in "${GLT_LABELS[@]}"; do
        run_chauffeur "${label}#0" "${CHAUFFEUR_DIR}/${label}"
    done
else
    # If no GLTs, loop through stim labels for AM2 models (e.g., SCR#0, SCR#1)
    for label in "${STIM_LABELS[@]}"; do
        run_chauffeur "${label}#0" "${CHAUFFEUR_DIR}/${label}#0"
        run_chauffeur "${label}#1" "${CHAUFFEUR_DIR}/${label}#1"
    done
fi

echo "--- GLM Analysis for ${SUBJECT} Complete ---"
