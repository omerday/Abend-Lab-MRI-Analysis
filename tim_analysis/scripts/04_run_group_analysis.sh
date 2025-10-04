#!/bin/bash

# --- Script: 04_run_group_analysis.sh ---
# Description: Runs group-level analysis (3dttest++) for a given model.
# Date: 2025-09-18

set -e # Exit immediately if a command exits with a non-zero status.

# Default values
ANALYSIS_NAME=""
INPUT_DIR=""
OUTPUT_DIR=""
SUBJECTS=""
SESSION="1"
REGRESSOR=""
LABEL=""

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --analysis) ANALYSIS_NAME="$2"; shift 2;;
        --input) INPUT_DIR="$2"; shift 2;;
        --output) OUTPUT_DIR="$2"; shift 2;;
        --subjects) SUBJECTS="$2"; shift 2;;
        --session) SESSION="$2"; shift 2;;
        --regressor) REGRESSOR="$2"; shift 2;;
        --label) LABEL="$2"; shift 2;;
        *) echo "Unknown option: $1"; exit 1;;
    esac
done

# Validate required arguments
if [ -z "$ANALYSIS_NAME" ] || [ -z "$INPUT_DIR" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$SUBJECTS" ] || [ -z "$SESSION" ] || [ -z "$REGRESSOR" ] || [ -z "$LABEL" ]; then
    echo "Usage: $0 --analysis <name> --input <dir> --output <dir> --subjects <sub1,sub2,...> --session <N> --regressor <reg> --label <label>"
    exit 1
fi

echo "--- Starting Group Analysis for ${ANALYSIS_NAME} ---"

GROUP_ANALYSIS_DIR="${OUTPUT_DIR}/group_analysis/${ANALYSIS_NAME}"
mkdir -p "$GROUP_ANALYSIS_DIR"
cd "$GROUP_ANALYSIS_DIR"

if [ ! -f MNI152_2009_template.nii.gz ]; then
    echo "Copying MNI152_2009_template.nii.gz..."
    cp ~/MNI152_2009_template.nii.gz .
fi

IFS=',' read -r -a subject_ids <<< "$SUBJECTS"

echo "Subjects: ${subject_ids[@]}"

DSETS=""
MASK_FILES=""
for subject in "${subject_ids[@]}"; do
    SESSION_PREFIX="ses-${SESSION}"
    PREPROC_RESULTS_DIR="${INPUT_DIR}/${subject}/${SESSION_PREFIX}/func/preproc/${subject}_preproc.results"
    GLM_RESULTS_DIR="${INPUT_DIR}/${subject}/${SESSION_PREFIX}/${ANALYSIS_NAME}/${subject}_${ANALYSIS_NAME}.results"
    
    STATS_FILE="${GLM_RESULTS_DIR}/stats.${subject}_${ANALYSIS_NAME}+tlrc"
    MASK_FILE="${PREPROC_RESULTS_DIR}/mask_epi_anat.${subject}_preproc+tlrc"

    if [ ! -f "${STATS_FILE}.HEAD" ]; then
        echo "Warning: Stats file not found for ${subject}, skipping: ${STATS_FILE}.HEAD"
        continue
    fi
    if [ ! -f "${MASK_FILE}.HEAD" ]; then
        echo "Warning: Mask file not found for ${subject}, skipping: ${MASK_FILE}.HEAD"
        continue
    fi

    DSETS+=" ${subject} ${STATS_FILE}[${REGRESSOR}]"
    MASK_FILES+=" ${MASK_FILE}"
done

if [ -z "$DSETS" ]; then
    echo "No valid subject data found. Aborting group analysis."
    exit 1
fi

echo "Creating group mask..."
if [ -f group_mask+tlrc.HEAD ]; then
    echo "Group mask already exists. Deleting existing mask."
    rm group_mask+tlrc.*
fi
3dmask_tool -input ${MASK_FILES} -prefix group_mask -frac 0.5

TTEST_PREFIX="3dttest_${LABEL}"
echo "Running 3dttest++..."
if [ -f "${TTEST_PREFIX}+tlrc.HEAD" ]; then
    echo "T-test output already exists. Deleting existing output."
    rm "${TTEST_PREFIX}+tlrc".*
fi
3dttest++ -ClustSim -prefix "$TTEST_PREFIX" \
    -setA "${LABEL}" ${DSETS}

echo "Masking results..."
if [ -f "${TTEST_PREFIX}_masked+tlrc.HEAD" ]; then
    echo "Masked results already exist. Deleting existing mask."
    rm "${TTEST_PREFIX}_masked+tlrc".*
fi
3dcalc -a "${TTEST_PREFIX}+tlrc" \
       -b group_mask+tlrc \
       -expr 'a*b' \
       -prefix "${TTEST_PREFIX}_masked"

echo "Generating images with @chauffeur_afni..."
CHAUFFEUR_DIR="chauffeur_images"
mkdir -p "$CHAUFFEUR_DIR"

ZCSR_SUBBRICK="${LABEL}_Zscr" 

@chauffeur_afni \
    -ulay MNI152_2009_template.nii.gz \
    -ulay_range 0% 130% \
    -olay "./${TTEST_PREFIX}_masked+tlrc.HEAD" \
    -box_focus_slices AMASK_FOCUS_ULAY \
    -func_range 3 \
    -cbar Reds_and_Blues_Inv \
    -thr_olay_p2stat 0.05 \
    -thr_olay_pside bisided \
    -olay_alpha Yes \
    -olay_boxed Yes \
    -set_subbricks -1 "${ZCSR_SUBBRICK}" "${ZCSR_SUBBRICK}" \
    -set_dicom_xyz -20 -8 -16 \
    -delta_slices 6 15 10 \
    -opacity 5 \
    -prefix "${CHAUFFEUR_DIR}/${LABEL}" \
    -set_xhairs OFF \
    -montx 3 -monty 3 \
    -label_mode 1 -label_size 4

echo "--- Backing up chauffeur images to Dropbox ---"

DROPBOX_ANALYSIS_DIR=~/Dropbox/group_${ANALYSIS_NAME}_${LABEL}
CHAUFFEUR_SOURCE_DIR="./chauffeur_images"
DEST_DIR="${DROPBOX_ANALYSIS_DIR}/chauffeur"

if [ -d ~/Dropbox ]; then
    mkdir -p "$DROPBOX_ANALYSIS_DIR"
    if [ -d "$CHAUFFEUR_SOURCE_DIR" ]; then
        echo "Copying chauffeur images to ${DEST_DIR}"
        # Clean up old chauffeur images if they exist
        if [ -d "$DEST_DIR" ]; then
            rm -rf "$DEST_DIR"
        fi
        cp -R "$CHAUFFEUR_SOURCE_DIR" "$DEST_DIR"
    else
        echo "WARNING: Chauffeur images directory not found at ${CHAUFFEUR_SOURCE_DIR}. Skipping copy."
    fi
else
    echo "WARNING: Dropbox directory not found at ~/Dropbox. Skipping copy."
fi

echo "--- Group Analysis for ${ANALYSIS_NAME} Complete ---"
