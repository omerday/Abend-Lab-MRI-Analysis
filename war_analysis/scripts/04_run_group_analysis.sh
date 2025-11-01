#!/bin/bash

# --- Script: 04_run_group_analysis.sh ---
# Description: Runs a group-level analysis (3dttest++ or 3dLMEr).

set -e # Exit immediately if a command exits with a non-zero status.

# Default values
ANALYSIS_TYPE=""
OUTPUT_PREFIX=""
MASK=""
DATA_TABLE_FILE=""
MODEL=""
GLT_CODES=""
SET_A_LABEL=""
SET_A_FILES=""

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --type) ANALYSIS_TYPE="$2"; shift 2;; 
        --output_prefix) OUTPUT_PREFIX="$2"; shift 2;; 
        --mask) MASK="$2"; shift 2;; 
        --data_table) DATA_TABLE_FILE="$2"; shift 2;; 
        --model) MODEL="$2"; shift 2;; 
        --glt_codes) GLT_CODES="$2"; shift 2;; 
        --setA_label) SET_A_LABEL="$2"; shift 2;; 
        --setA_files) SET_A_FILES="$2"; shift 2;; 
        *) echo "Unknown option: $1"; exit 1;; 
    esac
done

# Validate required arguments
if [ -z "$ANALYSIS_TYPE" ] || [ -z "$OUTPUT_PREFIX" ] || [ -z "$MASK" ]; then
    echo "Usage: $0 --type <type> --output_prefix <prefix> --mask <file> [options]"
    exit 1
fi

# Find the MNI template. Assume it's in the parent directory of the project.
MNI_TEMPLATE=$(find .. -name "MNI152_2009_template.nii.gz" | head -n 1)
if [ -z "$MNI_TEMPLATE" ]; then
    echo "Error: MNI152_2009_template.nii.gz not found." >&2
    exit 1
fi

echo "--- Starting Group Analysis: ${OUTPUT_PREFIX} ---"
echo "Analysis Type: ${ANALYSIS_TYPE}"

# Run analysis based on type
if [ "$ANALYSIS_TYPE" == "3dLMEr" ]; then
    if [ -z "$DATA_TABLE_FILE" ] || [ -z "$MODEL" ]; then
        echo "Error: --data_table and --model are required for 3dLMEr."
        exit 1
    fi
    
    echo "Model: ${MODEL}"
    echo "Data Table: ${DATA_TABLE_FILE}"

    3dLMEr -prefix "$OUTPUT_PREFIX" \
        -mask "$MASK" \
        -SS_type 3 \
        -model "$MODEL" \
        ${GLT_CODES} \
        -dataTable -`cat "$DATA_TABLE_FILE"`

elif [ "$ANALYSIS_TYPE" == "3dttest++" ]; then
    if [ -z "$SET_A_LABEL" ] || [ -z "$SET_A_FILES" ]; then
        echo "Error: --setA_label and --setA_files are required for 3dttest++."
        exit 1
    fi

    3dttest++ -prefix "$OUTPUT_PREFIX" \
        -mask "$MASK" \
        -setA "$SET_A_LABEL" ${SET_A_FILES}

else
    echo "Error: Unknown analysis type '${ANALYSIS_TYPE}'"
    exit 1
fi

echo "--- Group Analysis Complete. Output: ${OUTPUT_PREFIX}+tlrc ---"

echo "--- Generating report images with @chauffeur_afni ---"
CHAUFFEUR_DIR="chauffeur_images"
mkdir -p "$CHAUFFEUR_DIR"

# This part is a placeholder for generating specific images.
# The controller script will need to call this for each contrast of interest.
# For now, we just confirm the script ran.
echo "Chauffeur image generation would run here."

echo "--- Script Finished ---"