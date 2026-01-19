#!/bin/bash

# --- Script: 01_preprocess_anat.sh ---
# Description: Runs anatomical preprocessing (SSWarper) for a single subject.

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
ANAT_INPUT_FILE="${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/anat/${SUBJECT}_${SESSION_PREFIX}_T1w.nii.gz"
ANAT_OUTPUT_DIR="${OUTPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/anat_warped"

# Find the MNI template. Assume it's in the parent directory of the project.
MNI_TEMPLATE=${INPUT_DIR}/MNI152_2009_template_SSW.nii.gz
if [ -z "$MNI_TEMPLATE" ]; then
    log_error "MNI152_2009_template.nii.gz not found in parent directory of input."
    exit 1
fi

print_header "Starting Anatomical Preprocessing for ${SUBJECT}, ${SESSION_PREFIX}"

# Check if input anatomical file exists
if [ ! -f "$ANAT_INPUT_FILE" ]; then
    log_error "Anatomical file not found at ${ANAT_INPUT_FILE}"
    exit 1
fi

# Clean up previous output directory if it exists
if [ -d "$ANAT_OUTPUT_DIR" ]; then
    log_warn "Found existing anat_warped folder, deleting it: ${ANAT_OUTPUT_DIR}"
    rm -rf "$ANAT_OUTPUT_DIR"
fi

# Create the output directory
mkdir -p "$ANAT_OUTPUT_DIR"

log_info "Running SSWarper on ${SUBJECT}"
sswarper2 \
    -input "$ANAT_INPUT_FILE" \
    -base MNI152_2009_template_SSW.nii.gz \
    -subid "$SUBJECT" \
    -odir "$ANAT_OUTPUT_DIR" \
    -giant_move \
    -cost_nl_final lpa \
    -minp 8

log_success "Anatomical Preprocessing for ${SUBJECT} Complete"
