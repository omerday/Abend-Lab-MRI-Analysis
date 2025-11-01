#!/bin/bash

# --- Script: 01_preprocess_anat.sh ---
# Description: Runs anatomical preprocessing (SSWarper) for a single subject.

set -e # Exit immediately if a command exits with a non-zero status.

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
        *) echo "Unknown option: $1" >&2; exit 1;;
    esac
done

# Validate required arguments
if [ -z "$SUBJECT" ] || [ -z "$SESSION" ] || [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ]; then
    echo "Usage: $0 --subject <ID> --session <N> --input <dir> --output <dir>" >&2
    exit 1
fi

SESSION_PREFIX="ses-${SESSION}"
ANAT_INPUT_FILE="${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/anat/${SUBJECT}_${SESSION_PREFIX}_T1w.nii.gz"
ANAT_OUTPUT_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/anat_warped"

# Find the MNI template. Assume it's in the parent directory of the project.
MNI_TEMPLATE=$(find "${INPUT_DIR}/.." -name "MNI152_2009_template.nii.gz" | head -n 1)
if [ -z "$MNI_TEMPLATE" ]; then
    echo "Error: MNI152_2009_template.nii.gz not found in parent directory of input." >&2
    exit 1
fi

echo "--- Starting Anatomical Preprocessing for ${SUBJECT}, ${SESSION_PREFIX} ---"

# Check if input anatomical file exists
if [ ! -f "$ANAT_INPUT_FILE" ]; then
    echo "Error: Anatomical file not found at ${ANAT_INPUT_FILE}" >&2
    exit 1
fi

# Clean up previous output directory if it exists
if [ -d "$ANAT_OUTPUT_DIR" ]; then
    echo "Found existing anat_warped folder, deleting it: ${ANAT_OUTPUT_DIR}"
    rm -rf "$ANAT_OUTPUT_DIR"
fi

# Create the output directory
mkdir -p "$ANAT_OUTPUT_DIR"

echo "Running SSWarper on ${SUBJECT}"
sswarper2 \
    -input "$ANAT_INPUT_FILE" \
    -base "$MNI_TEMPLATE" \
    -subid "$SUBJECT" \
    -odir "$ANAT_OUTPUT_DIR" \
    -giant_move \
    -cost_nl_final lpa \
    -minp 8

echo "--- Anatomical Preprocessing for ${SUBJECT} Complete ---"
