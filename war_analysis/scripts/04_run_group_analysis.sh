#!/bin/bash

# --- Script: 04_run_group_analysis.sh ---
# Description: Runs a group-level analysis (3dttest++ or 3dLMEr).

set -ex # Exit immediately if a command exits with a non-zero status.

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

echo "Starting from path `pwd`"

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

    CMD="3dLMEr -prefix \"$OUTPUT_PREFIX\" \
        -mask \"$MASK\" \
        -SS_type 3 \
        -model \"$MODEL\" \
        ${GLT_CODES} \
        -dataTable @\"$DATA_TABLE_FILE\" \
        -resid \"${OUTPUT_PREFIX}_resid\""

    echo "Executing: $CMD"
    if [ -f "${OUTPUT_PREFIX}+tlrc.HEAD" ]; then
        echo "Output dataset ${OUTPUT_PREFIX}+tlrc.HEAD already exists. Skipping 3dLMEr execution."
    else
        eval $CMD
    fi
    
    if [ $? -eq 0 ]; then
        echo "--- Running ClustSim Correction ---"
        RESID_FILE="${OUTPUT_PREFIX}_resid+tlrc"
        
        if [ -f "${RESID_FILE}.HEAD" ]; then
             # Calculate ACF parameters
             echo "Calculating ACF parameters..."
             ACF_PARAMS=$(3dFWHMx -mask "$MASK" -input "$RESID_FILE" -acf NULL | tail -n 1)
             echo "ACF Params: $ACF_PARAMS"
             
             # Extract a, b, c (first 3 values)
             # The output might have 4 values (a, b, c, FWHM). We need the first 3.
             read -r a b c fwhm <<< "$ACF_PARAMS"
             
             echo "Running 3dClustSim with ACF: $a $b $c"
             3dClustSim -mask "$MASK" -acf $a $b $c -both -prefix "${OUTPUT_PREFIX}_ClustSim"
             
             CMD_FILE="${OUTPUT_PREFIX}_ClustSim.cmd"
             
             # Check for generic output filename (common in some AFNI versions)
             if [ ! -f "$CMD_FILE" ]; then
                 OUTPUT_DIR=$(dirname "$OUTPUT_PREFIX")
                 if [ -f "${OUTPUT_DIR}/3dClustSim.cmd" ]; then
                     echo "Found generic 3dClustSim.cmd, renaming to match prefix..."
                     mv "${OUTPUT_DIR}/3dClustSim.cmd" "${CMD_FILE}"
                 fi
             fi

             if [ -f "${CMD_FILE}" ]; then
                 echo "Attaching ClustSim tables to output..."
                 # 3dClustSim.cmd contains the 3drefit command but lacks the dataset argument.
                 # We read the command and append the dataset.
                 CLUSTSIM_CMD=$(cat "${CMD_FILE}")
                 $CLUSTSIM_CMD "${OUTPUT_PREFIX}+tlrc"
                 
                 # Clean up ClustSim intermediate files
                #  rm "${OUTPUT_PREFIX}_ClustSim"*
             else
                 echo "Error: 3dClustSim failed to generate .cmd file."
             fi
             
             # Clean up residuals to save space (optional, but recommended for large analyses)
             # rm "${RESID_FILE}"* 
        else
             echo "Warning: Residual file not found. Skipping ClustSim."
        fi
    fi

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
CHAUFFEUR_DIR="${OUTPUT_PREFIX}_images"
mkdir -p "$CHAUFFEUR_DIR"

if [ -f "${OUTPUT_PREFIX}+tlrc.HEAD" ]; then
    # Get all sub-brick labels
    LABELS=$(3dinfo -label "${OUTPUT_PREFIX}+tlrc")
    IFS='|' read -r -a LABEL_ARRAY <<< "$LABELS"

    for label in "${LABEL_ARRAY[@]}"; do
        # Clean up label (remove leading/trailing spaces)
        label=$(echo "$label" | xargs)
        
        STAT_LABEL=""
        INTEN_LABEL=""
        
        # Identify statistic sub-bricks
        if [[ "$label" == *" Z" ]]; then
            STAT_LABEL="$label"
            INTEN_LABEL="${label% Z}"
        elif [[ "$label" == *" Tstat" ]]; then
            STAT_LABEL="$label"
            INTEN_LABEL="${label% Tstat}"
        elif [[ "$label" == *" F" ]]; then
            STAT_LABEL="$label"
            INTEN_LABEL="${label% F}"
        elif [[ "$label" == *" Chi-sq" ]]; then
            STAT_LABEL="$label"
            INTEN_LABEL="${label% Chi-sq}"
        elif [[ "$label" == *"_Tstat" ]]; then
            # Common in 3dttest++ (e.g., SetA_Tstat -> SetA_mean)
            STAT_LABEL="$label"
            INTEN_LABEL="${label%_Tstat}_mean"
        fi
        
        if [ -n "$STAT_LABEL" ]; then
            # Check if intensity label exists
            HAS_INTEN=0
            for l in "${LABEL_ARRAY[@]}"; do
                l=$(echo "$l" | xargs)
                if [ "$l" == "$INTEN_LABEL" ]; then
                    HAS_INTEN=1
                    break
                fi
            done
            
            SUBBRICKS_ARG=()
            if [ "$HAS_INTEN" -eq 1 ]; then
                 SUBBRICKS_ARG=(-set_subbricks -1 "$INTEN_LABEL" "$STAT_LABEL")
            else
                 # Fallback: Use stat for both
                 SUBBRICKS_ARG=(-set_subbricks -1 "$STAT_LABEL" "$STAT_LABEL")
            fi

            SAFE_NAME=$(echo "$INTEN_LABEL" | tr ' :' '__')
            # Fallback if INTEN_LABEL was empty or just spaces
            if [ -z "$SAFE_NAME" ]; then SAFE_NAME=$(echo "$STAT_LABEL" | tr ' :' '__'); fi

            echo "Generating image for: $SAFE_NAME ($STAT_LABEL)"
            
            set +e # Don't exit on single image failure
            @chauffeur_afni \
                -ulay               "$MNI_TEMPLATE" \
                -ulay_range         0% 130% \
                -olay               "${OUTPUT_PREFIX}+tlrc" \
                -box_focus_slices   AMASK_FOCUS_ULAY \
                -func_range         3 \
                -cbar               Reds_and_Blues_Inv \
                -thr_olay_p2stat    0.05 \
                -thr_olay_pside     bisided \
                -olay_alpha         Yes \
                -olay_boxed         Yes \
                "${SUBBRICKS_ARG[@]}" \
                -opacity            5 \
                -zerocolor          white \
                -set_dicom_xyz -20 -8 -16 \
                -delta_slices 6 15 10 \
                -clusterize "-NN 2 -clust_nvox 35" \
                -prefix             "${CHAUFFEUR_DIR}/${SAFE_NAME}" \
                -set_xhairs         OFF \
                -label_mode         1 \
                -label_size         3 \
                -montx 3 -monty 3 \
                -do_clean
            set -e
        fi
    done
else
    echo "Warning: Output dataset ${OUTPUT_PREFIX}+tlrc.HEAD not found."
fi

echo "--- Script Finished ---"