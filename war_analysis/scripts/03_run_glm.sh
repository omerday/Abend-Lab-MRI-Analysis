#!/bin/bash

# --- Script: 03_run_glm.sh ---
# Description: Runs a specific GLM analysis on preprocessed data.

set -e # Exit immediately if a command exits with a non-zero status.

# Default values
SUBJECT=""
SESSION="1"
INPUT_DIR=""
OUTPUT_DIR=""
ANALYSIS_NAME=""

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --subject) SUBJECT="$2"; shift 2;;
        --session) SESSION="$2"; shift 2;;
        --input) INPUT_DIR="$2"; shift 2;;
        --output) OUTPUT_DIR="$2"; shift 2;;
        --analysis) ANALYSIS_NAME="$2"; shift 2;;
        *) echo "Unknown option: $1" >&2; exit 1;;
    esac
done

# Validate required arguments
if [ -z "$SUBJECT" ] || [ -z "$SESSION" ] || [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$ANALYSIS_NAME" ]; then
    echo "Usage: $0 --subject <ID> --session <N> --input <dir> --output <dir> --analysis <name>" >&2
    exit 1
fi

SESSION_PREFIX="ses-${SESSION}"
PREPROC_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func_preproc/${SUBJECT}_preproc.results"
GLM_OUTPUT_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/glm/${ANALYSIS_NAME}"
TIMING_DIR="${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func"
CONFIG_FILE="analysis_configs/analysis_models.toml"

# --- Load Model Configuration from TOML file ---
# This uses a simple awk parser. For complex configs, a proper tool might be better.
MODEL_CONFIG=$(awk -v model="$ANALYSIS_NAME" '/^\[/{in_model=0} $0=="["model"]"{in_model=1} in_model' "$CONFIG_FILE")

STIM_FILES_RAW=$(echo "$MODEL_CONFIG" | awk '/stim_files = \[/{f=1;next} /]/{f=0} f' | tr -d ',"' | tr -d ' ' | paste -sd, -)
STIM_LABELS_RAW=$(echo "$MODEL_CONFIG" | grep 'stim_labels' | sed 's/stim_labels = \[\(.*\)\]/\1/' | tr -d '"' | sed 's/ //g')
BASIS=$(echo "$MODEL_CONFIG" | grep 'basis' | sed 's/basis = "\(.*\)"/\1/')
STIM_TYPES=$(echo "$MODEL_CONFIG" | grep 'stim_types' | sed 's/stim_types = "\(.*\)".*/\1/')

IFS=',' read -r -a STIM_FILES <<< "$STIM_FILES_RAW"
IFS=',' read -r -a STIM_LABELS <<< "$STIM_LABELS_RAW"

STIM_PATHS=()
for file in "${STIM_FILES[@]}"; do
    STIM_PATHS+=("${TIMING_DIR}/${file}")
done
REGRESS_STIM_TIMES_ARGS=("-regress_stim_times" "${STIM_PATHS[@]}")

REGRESS_STIM_LABELS_ARGS=("-regress_stim_labels" "${STIM_LABELS[@]}")

# Construct GLT arguments
GLT_ARGS=""
i=1
while IFS= read -r line; do
    if [[ $line == *"sym ="* ]]; then
        sym=$(echo "$line" | sed -e 's/.*sym = "\(.*\)".*/\1/')
    elif [[ $line == *"label ="* ]]; then
        label=$(echo "$line" | sed -e 's/.*label = "\(.*\)".*/\1/')
        GLT_ARGS+="-gltsym 'SYM: ${sym}' -glt_label ${i} ${label} "
        i=$((i+1))
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

# Conditionally add stim types
STIM_TYPES_ARG=""
if [ -n "$STIM_TYPES" ]; then
    STIM_TYPES_ARG="-regress_stim_types $STIM_TYPES"
fi

# Run afni_proc.py for the GLM
afni_proc.py \
    -subj_id "${SUBJECT}_${ANALYSIS_NAME}" \
    -dsets ${PREPROC_DIR}/pb05.${SUBJECT}_preproc.r*.scale+tlrc.HEAD \
    -blocks regress \
    "${REGRESS_STIM_TIMES_ARGS[@]}" \
    "${REGRESS_STIM_LABELS_ARGS[@]}" \
    ${STIM_TYPES_ARG} \
    -regress_basis "$BASIS" \
    ${GLT_ARGS} \
    -regress_opts_3dD -jobs 8 \
    -regress_motion_file "${PREPROC_DIR}/dfile_rall.1D" \
    -regress_motion_per_run \
    -regress_censor_motion 0.5 \
    -regress_censor_outliers 0.05 \
    -regress_reml_exec \
    -regress_no_mask \
    -regress_compute_fitts \
    -regress_make_ideal_sum sum_ideal.1D \
    -regress_run_clustsim no \
    -remove_preproc_files \
    -execute

echo "--- GLM Analysis for ${SUBJECT} Complete ---"

echo "--- Exporting QC images using @chauffeur_afni ---"
QC_DIR="QC"
mkdir -p "$QC_DIR"

for stim in "${STIM_LABELS[@]}"; do
    @chauffeur_afni                                             \
        -ulay               "../../func_preproc/${SUBJECT}_preproc.results/anat_final.${SUBJECT}_preproc+tlrc.HEAD"      \
        -ulay_range         0% 130%                             \
        -olay               "${SUBJECT}_${ANALYSIS_NAME}.results/stats.${SUBJECT}_${ANALYSIS_NAME}+tlrc.HEAD"   \
        -box_focus_slices   AMASK_FOCUS_ULAY                    \
        -func_range         3                                   \
        -cbar               Reds_and_Blues_Inv                  \
        -thr_olay_p2stat    0.05                                \
        -thr_olay_pside     bisided                             \
        -olay_alpha         Yes                                 \
        -olay_boxed         Yes                                 \
        -set_subbricks      -1 "${stim}#0_Coef" "${stim}#0_Tstat" \
        -set_dicom_xyz      -20 -8 -16                          \
        -delta_slices       6 15 10                             \
        -opacity            5                                   \
        -prefix             "${QC_DIR}/${stim}"             \
        -set_xhairs         OFF                                 \
        -montx 3 -monty 3                                       \
        -label_mode 1 -label_size 4
done
