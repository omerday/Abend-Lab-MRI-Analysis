#!/bin/bash

# --- Script: 03_run_glm.sh ---
# Description: Runs a specific GLM analysis on preprocessed data.

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
ANALYSIS_NAME=""

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --subject) SUBJECT="$2"; shift 2;;
        --session) SESSION="$2"; shift 2;;
        --input) INPUT_DIR="$2"; shift 2;;
        --output) OUTPUT_DIR="$2"; shift 2;;
        --analysis) ANALYSIS_NAME="$2"; shift 2;;
        *) log_error "Unknown option: $1"; exit 1;;
    esac
done

# Validate required arguments
if [ -z "$SUBJECT" ] || [ -z "$SESSION" ] || [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$ANALYSIS_NAME" ]; then
    log_error "Usage: $0 --subject <ID> --session <N> --input <dir> --output <dir> --analysis <name>"
    exit 1
fi

SESSION_PREFIX="ses-${SESSION}"
PREPROC_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func_preproc/${SUBJECT}_preproc.results"
GLM_OUTPUT_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/glm/${ANALYSIS_NAME}"
TIMING_DIR="${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="${SCRIPT_DIR}/../analysis_configs/analysis_models.toml"
fi

if [ ! -f "$CONFIG_FILE" ]; then
    log_error "Config file not found at ${CONFIG_FILE}"
    exit 1
fi

# --- Load Model Configuration from TOML file using Python ---
eval "$(python3 -c "
import toml, sys, shlex

try:
    with open('$CONFIG_FILE') as f:
        data = toml.load(f)
    model = data.get('$ANALYSIS_NAME')
    if not model:
        sys.stderr.write(f'Model $ANALYSIS_NAME not found in $CONFIG_FILE\n')
        sys.exit(1)
    
    stim_files = [f'$TIMING_DIR/{s}' for s in model.get('stim_files', [])]
    stim_labels = model.get('stim_labels', [])
    basis = model.get('basis', '')
    stim_types = model.get('stim_types', '')
    
    stim_files_str = ' '.join(shlex.quote(s) for s in stim_files)
    stim_labels_str = ' '.join(shlex.quote(s) for s in stim_labels)
    
    glt_str = ''
    for i, g in enumerate(model.get('glt', []), 1):
        sym = g.get('sym', '')
        label = g.get('label', '')
        glt_str += f\"-gltsym 'SYM: {sym}' -glt_label {i} {label} \"
    
    print(f'STIM_PATHS=({stim_files_str})')
    print(f'STIM_LABELS=({stim_labels_str})')
    print(f'BASIS={shlex.quote(basis)}')
    print(f'STIM_TYPES={shlex.quote(stim_types)}')
    print(f'GLT_ARGS={shlex.quote(glt_str)}')
except Exception as e:
    sys.stderr.write(str(e) + '\n')
    sys.exit(1)
")"

if [ ${#STIM_PATHS[@]} -eq 0 ]; then
    log_error "No stim_files found for model '${ANALYSIS_NAME}' in ${CONFIG_FILE}"
    exit 1
fi

REGRESS_STIM_TIMES_ARGS=("-regress_stim_times" "${STIM_PATHS[@]}")
REGRESS_STIM_LABELS_ARGS=("-regress_stim_labels" "${STIM_LABELS[@]}")


print_header "Starting GLM Analysis (${ANALYSIS_NAME}) for ${SUBJECT}, ${SESSION_PREFIX}"

# Clean up previous output directory
if [ -d "$GLM_OUTPUT_DIR" ]; then
    log_warn "Found existing GLM folder, deleting it: ${GLM_OUTPUT_DIR}"
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

log_success "GLM Analysis for ${SUBJECT} Complete"

print_subheader "Masking statistical output for chauffeur"
RESULTS_DIR="${SUBJECT}_${ANALYSIS_NAME}.results"
STATS_FILE="${RESULTS_DIR}/stats.${SUBJECT}_${ANALYSIS_NAME}+tlrc"
MASK_FILE="${PREPROC_DIR}/mask_epi_anat.${SUBJECT}_preproc+tlrc"
MASKED_STATS_FILE="${RESULTS_DIR}/masked_stats.${SUBJECT}_${ANALYSIS_NAME}"

OLAY_DATASET="${STATS_FILE}.HEAD"
if [ -f "${MASK_FILE}.HEAD" ]; then
    log_info "Applying brain mask ${MASK_FILE} to ${STATS_FILE}..."
    3dcalc \
        -a "${STATS_FILE}" \
        -b "${MASK_FILE}" \
        -exp 'a*b' \
        -prefix "${MASKED_STATS_FILE}" \
        -overwrite
    OLAY_DATASET="${MASKED_STATS_FILE}+tlrc.HEAD"
else
    log_warn "Mask file not found at ${MASK_FILE}.HEAD. Proceeding with unmasked stats."
fi

print_subheader "Exporting QC images using @chauffeur_afni"
QC_DIR="QC"
mkdir -p "$QC_DIR"

for stim in "${STIM_LABELS[@]}"; do
    @chauffeur_afni                                             \
        -ulay               "../../func_preproc/${SUBJECT}_preproc.results/anat_final.${SUBJECT}_preproc+tlrc.HEAD"      \
        -ulay_range         0% 130%                             \
        -olay               "${OLAY_DATASET}"                   \
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
        -prefix             "${QC_DIR}/${stim}"                 \
        -set_xhairs         OFF                                 \
        -montx 3 -monty 3                                       \
        -label_mode 1 -label_size 4
done

