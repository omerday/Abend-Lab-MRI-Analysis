#!/bin/bash

# --- Script: 04_run_group_analysis.sh ---
# Description: Runs group-level analysis (3dttest++ or 3dLMEr).
# This is a template and will be expanded based on the specific group analysis model.

set -e # Exit immediately if a command exits with a non-zero status.

# Default values
ANALYSIS_NAME=""
INPUT_DIR=""
OUTPUT_DIR=""
SUBJECTS=""
SESSION="1"

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --analysis) ANALYSIS_NAME="$2"; shift 2;;
        --input) INPUT_DIR="$2"; shift 2;;
        --output) OUTPUT_DIR="$2"; shift 2;;
        --subjects) SUBJECTS="$2"; shift 2;;
        --session) SESSION="$2"; shift 2;;
        *) echo "Unknown option: $1"; exit 1;;
    esac
done

# Validate required arguments
if [ -z "$ANALYSIS_NAME" ] || [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$SUBJECTS" ] || [ -z "$SESSION" ]; then
    echo "Usage: $0 --analysis <name> --input <dir> --output <dir> --subjects <sub1,sub2,...> --session <N>" >&2
    exit 1
fi

echo "--- Starting Group Analysis for ${ANALYSIS_NAME} ---"

GROUP_ANALYSIS_DIR="${OUTPUT_DIR}/group_analysis/${ANALYSIS_NAME}"
mkdir -p "$GROUP_ANALYSIS_DIR"
cd "$GROUP_ANALYSIS_DIR"

# This script is a placeholder. The actual implementation will depend on the
# specific group analysis model (e.g., 3dttest++, 3dLMEr) and will be
# orchestrated by the run_group_level.py controller, which will pass
# the appropriate commands and data tables.

echo "Group analysis script is a placeholder. Implementation will be model-specific."

# Example of creating a group mask (common step)
# IFS=',' read -r -a subject_ids <<< "$SUBJECTS"
# MASK_FILES=""
# for subject in "${subject_ids[@]}"; do
#     MASK_FILES+=" ${INPUT_DIR}/${subject}/ses-${SESSION}/func_preproc/${subject}_preproc.results/mask_epi_anat.${subject}_preproc+tlrc"
# done
# 3dmask_tool -input ${MASK_FILES} -prefix group_mask -frac 0.5

echo "--- Group Analysis for ${ANALYSIS_NAME} Complete ---"
