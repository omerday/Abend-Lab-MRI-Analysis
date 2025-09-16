#!/bin/bash

# --- Script: run_group_analysis.sh ---
# Description: Runs a group-level t-test using 3dttest++.
# This script is intended to be called by a controller script like run_group_level.py.
# Date: 2025-09-16

set -e

# --- Argument Parsing ---
OUTPUT_DIR="."
LABEL="group_analysis"
SETA_LABEL=""
CONTRAST_NAME=""

# The script expects arguments in a specific order:
# 1. --output_dir <path>
# 2. --label <label>
# 3. --contrast_name <name>
# 4. --setA_label <label>
# 5. The rest of the arguments are the subject datasets.

while [[ "$1" =~ ^- ]]; do
    case "$1" in
        --output_dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --label)
            LABEL="$2"
            shift 2
            ;;
        --setA_label)
            SETA_LABEL="$2"
            shift 2
            ;;
        --contrast_name)
            CONTRAST_NAME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# All remaining arguments are the datasets for setA
SET_A_DSETS=("$@")

if [ ${#SET_A_DSETS[@]} -eq 0 ]; then
    echo "Error: No datasets provided for the analysis." >&2
    exit 1
fi

echo "--- Starting Group Analysis ---"
echo "Output Directory: ${OUTPUT_DIR}"
echo "Label: ${LABEL}"
echo "Contrast: ${SETA_LABEL}"

# --- Run 3dttest++ ---
# The output files will be created in the current directory, which is set
# to the group output directory by the calling python script.

PREFIX="${LABEL}_${CONTRAST_NAME}"

3dttest++ -prefix "${PREFIX}" \
    -setA "${SETA_LABEL}" \
    "${SET_A_DSETS[@]}"

echo "3dttest++ complete. Output prefix: ${PREFIX}"

# --- Visualization with @chauffeur_afni (optional) ---
# This part can be expanded or made more robust.

# Create a group mask (example using 3dmask_tool, may need adjustment)
# For simplicity, this is commented out, but can be added back with a proper
# way to find and specify mask files.
# MASK_FILES=...
# 3dmask_tool -input ${MASK_FILES} -prefix group_mask -frac 0.5
# 3dcalc -a ${PREFIX}+tlrc -b group_mask+tlrc -expr 'a*b' -prefix ${PREFIX}_masked

CHAUFFEUR_DIR="chauffeur"
mkdir -p "$CHAUFFEUR_DIR"

@chauffeur_afni \
    -ulay MNI152_2009_template.nii.gz \
    -olay "${PREFIX}+tlrc.HEAD" \
    -set_subbricks -1 "${SETA_LABEL}_Tstat" "${SETA_LABEL}_Tstat" \
    -prefix "${CHAUFFEUR_DIR}/${LABEL}" \
    -cbar Reds_and_Blues_Inv \
    -thr_olay_p2stat 0.05 \
    -thr_olay_pside bisided \
    -clusterize "-NN 2 -clust_nvox 40" \
    -montx 3 -monty 3 \
    -set_xhairs OFF

echo "--- Group Analysis Complete ---"
