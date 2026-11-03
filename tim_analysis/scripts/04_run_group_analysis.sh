#!/bin/bash

# --- Script: 04_run_group_analysis.sh ---
# Description: Runs a group-level analysis (3dttest++ with -clustsim or 3dLMEr) for TIM paradigm.

set -euo pipefail

# Get the directory where the script is located
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

# Source the color utility script
# shellcheck source=./utils_colors.sh
source "${SCRIPT_DIR}/utils_colors.sh"

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
        --type)
            ANALYSIS_TYPE="$2"
            shift 2
            ;;
        --output_prefix)
            OUTPUT_PREFIX="$2"
            shift 2
            ;;
        --mask)
            MASK="$2"
            shift 2
            ;;
        --data_table)
            DATA_TABLE_FILE="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --glt_codes)
            GLT_CODES="$2"
            shift 2
            ;;
        --setA_label)
            SET_A_LABEL="$2"
            shift 2
            ;;
        --setA_files)
            SET_A_FILES="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

log_info "Starting from working directory: $(pwd)"

# Validate required arguments
if [[ -z "${ANALYSIS_TYPE}" ]] || [[ -z "${OUTPUT_PREFIX}" ]] || [[ -z "${MASK}" ]]; then
    log_error "Usage: $0 --type <type> --output_prefix <prefix> --mask <file> [options]"
    exit 1
fi

# Find the MNI template via container path, SCRIPT_DIR, or parent search
MNI_TEMPLATE=""
for candidate in \
    "/opt/afni_templates/MNI152_2009_template.nii.gz" \
    "${SCRIPT_DIR}/../MNI152_2009_template.nii.gz" \
    "${SCRIPT_DIR}/../../tim_analysis/MNI152_2009_template.nii.gz"; do
    if [[ -f "${candidate}" ]]; then
        MNI_TEMPLATE="${candidate}"
        break
    fi
done

if [[ -z "${MNI_TEMPLATE}" ]]; then
    MNI_TEMPLATE=$(find "${SCRIPT_DIR}/../.." -name "MNI152_2009_template.nii.gz" 2>/dev/null | head -n 1)
fi

if [[ -z "${MNI_TEMPLATE}" ]] || [[ ! -f "${MNI_TEMPLATE}" ]]; then
    log_error "MNI152_2009_template.nii.gz not found."
    exit 1
fi

# Ensure working directory is the output directory and use relative output basename.
# This prevents AFNI fatal errors when relative paths are required (e.g. 3dttest++ -clustsim)
OUTPUT_DIR="$(dirname "${OUTPUT_PREFIX}")"
OUTPUT_BASE="$(basename "${OUTPUT_PREFIX}")"

mkdir -p "${OUTPUT_DIR}"
cd "${OUTPUT_DIR}"
OUTPUT_PREFIX="${OUTPUT_BASE}"

print_header "Starting Group Analysis: ${OUTPUT_PREFIX}"
log_info "Analysis Type: ${ANALYSIS_TYPE}"

# Run analysis based on type
if [[ "${ANALYSIS_TYPE}" == "3dLMEr" ]]; then
    if [[ -z "${DATA_TABLE_FILE}" ]] || [[ -z "${MODEL}" ]]; then
        log_error "--data_table and --model are required for 3dLMEr."
        exit 1
    fi

    log_info "Model: ${MODEL}"
    log_info "Data Table: ${DATA_TABLE_FILE}"

    CMD="3dLMEr -prefix \"$OUTPUT_PREFIX\" \
        -mask \"$MASK\" \
        -SS_type 3 \
        -model \"$MODEL\" \
        ${GLT_CODES} \
        -dataTable @\"$DATA_TABLE_FILE\" \
        -resid \"${OUTPUT_PREFIX}_resid\""

    run_clustsim=0
    if [[ -f "${OUTPUT_PREFIX}+tlrc.HEAD" ]]; then
        log_warn "Output dataset ${OUTPUT_PREFIX}+tlrc.HEAD already exists. Skipping 3dLMEr execution."
        run_clustsim=1
    else
        log_info "Executing: ${CMD}"
        if eval "${CMD}"; then
            run_clustsim=1
        else
            log_error "3dLMEr execution failed."
            exit 1
        fi
    fi

    if [[ "${run_clustsim}" -eq 1 ]]; then
        print_subheader "Running ClustSim Correction"
        RESID_FILE="${OUTPUT_PREFIX}_resid+tlrc"

        if [[ -f "${RESID_FILE}.HEAD" ]]; then
            # Calculate ACF parameters
            log_info "Calculating ACF parameters..."
            ACF_PARAMS=$(3dFWHMx -mask "${MASK}" -input "${RESID_FILE}" -acf NULL | tail -n 1)
            log_info "ACF Params: ${ACF_PARAMS}"

            # Extract a, b, c (first 3 values)
            read -r a b c fwhm <<< "${ACF_PARAMS}"

            log_info "Running 3dClustSim with ACF: ${a} ${b} ${c}"
            3dClustSim -mask "${MASK}" -acf "${a}" "${b}" "${c}" -both -prefix "${OUTPUT_PREFIX}_ClustSim"

            CMD_FILE="${OUTPUT_PREFIX}_ClustSim.cmd"

            # Check for generic output filename
            if [[ ! -f "${CMD_FILE}" ]]; then
                if [[ -f "${OUTPUT_DIR}/3dClustSim.cmd" ]]; then
                    log_warn "Found generic 3dClustSim.cmd, renaming to match prefix..."
                    mv "${OUTPUT_DIR}/3dClustSim.cmd" "${CMD_FILE}"
                fi
            fi

            if [[ -f "${CMD_FILE}" ]]; then
                log_info "Attaching ClustSim tables to output..."
                CLUSTSIM_CMD="$(cat "${CMD_FILE}")"
                $CLUSTSIM_CMD "${OUTPUT_PREFIX}+tlrc"
            else
                log_error "3dClustSim failed to generate .cmd file."
            fi
        else
            log_warn "Residual file not found. Skipping ClustSim."
        fi
    fi

elif [[ "${ANALYSIS_TYPE}" == "3dttest++" ]]; then
    if [[ -z "${SET_A_LABEL}" ]] || [[ -z "${SET_A_FILES}" ]]; then
        log_error "--setA_label and --setA_files are required for 3dttest++."
        exit 1
    fi

    read -r -a SET_A_FILES_ARR <<< "${SET_A_FILES}"

    if [[ -f "${OUTPUT_PREFIX}+tlrc.HEAD" ]]; then
        log_warn "Output dataset ${OUTPUT_PREFIX}+tlrc.HEAD already exists. Skipping 3dttest++ execution."
    else
        # TIM group analysis includes -clustsim on 3dttest++
        # -prefix must be a relative dataset name (no leading / or ../) when -clustsim is used
        3dttest++ -prefix "${OUTPUT_PREFIX}" \
            -mask "${MASK}" \
            -setA "${SET_A_LABEL}" "${SET_A_FILES_ARR[@]}" \
            -clustsim
    fi

else
    log_error "Unknown analysis type '${ANALYSIS_TYPE}'"
    exit 1
fi

log_success "Group Analysis Complete. Output: ${OUTPUT_PREFIX}+tlrc"

# Ensure headless Xvfb display is active for @chauffeur_afni
XVFB_LOCAL_PID=""
cleanup_xvfb() {
    if [[ -n "${XVFB_LOCAL_PID}" ]] && kill -0 "${XVFB_LOCAL_PID}" >/dev/null 2>&1; then
        kill "${XVFB_LOCAL_PID}" >/dev/null 2>&1 || true
    fi
}
trap cleanup_xvfb EXIT INT TERM

if command -v Xvfb >/dev/null 2>&1; then
    if [ -z "${DISPLAY:-}" ] || ! command -v xset >/dev/null 2>&1 || ! xset q >/dev/null 2>&1; then
        XVFB_DISPLAY=":99"
        log_info "Starting headless virtual framebuffer Xvfb on ${XVFB_DISPLAY} for @chauffeur_afni..."
        Xvfb "${XVFB_DISPLAY}" -screen 0 1600x1200x24 -nolisten tcp >/dev/null 2>&1 &
        XVFB_LOCAL_PID=$!
        export DISPLAY="${XVFB_DISPLAY}"
        sleep 1
    fi
fi

print_subheader "Generating report images with @chauffeur_afni"
CHAUFFEUR_DIR="${OUTPUT_PREFIX}_images"
mkdir -p "${CHAUFFEUR_DIR}"

if [[ -f "${OUTPUT_PREFIX}+tlrc.HEAD" ]]; then
    # Get all sub-brick labels
    LABELS=$(3dinfo -label "${OUTPUT_PREFIX}+tlrc")
    IFS='|' read -r -a LABEL_ARRAY <<< "${LABELS}"

    for label in "${LABEL_ARRAY[@]}"; do
        # Clean up label (remove leading/trailing spaces)
        label=$(echo "${label}" | xargs)

        STAT_LABEL=""
        INTEN_LABEL=""

        # Identify statistic sub-bricks
        if [[ "${label}" == *" Z" ]]; then
            STAT_LABEL="${label}"
            INTEN_LABEL="${label% Z}"
        elif [[ "${label}" == *" Tstat" ]]; then
            STAT_LABEL="${label}"
            INTEN_LABEL="${label% Tstat}"
        elif [[ "${label}" == *" F" ]]; then
            STAT_LABEL="${label}"
            INTEN_LABEL="${label% F}"
        elif [[ "${label}" == *" Chi-sq" ]]; then
            STAT_LABEL="${label}"
            INTEN_LABEL="${label% Chi-sq}"
        elif [[ "${label}" == *"_Tstat" ]]; then
            # Common in 3dttest++ (e.g., SetA_Tstat -> SetA_mean)
            STAT_LABEL="${label}"
            INTEN_LABEL="${label%_Tstat}_mean"
        elif [[ "${label}" == *"_Zscore" ]]; then
            STAT_LABEL="${label}"
            INTEN_LABEL="${label%_Zscore}_mean"
        elif [[ "${label}" == *"_Zscr" ]]; then
            # From 3dttest++ -clustsim or -toz (e.g., SetA_Zscr -> SetA_mean)
            STAT_LABEL="${label}"
            INTEN_LABEL="${label%_Zscr}_mean"
        elif [[ "${label}" == *"_Fstat" ]]; then
            STAT_LABEL="${label}"
            INTEN_LABEL="${label%_Fstat}_mean"
        fi

        if [[ -n "${STAT_LABEL}" ]]; then
            # Check if intensity label exists
            HAS_INTEN=0
            for l in "${LABEL_ARRAY[@]}"; do
                l=$(echo "${l}" | xargs)
                if [[ "${l}" == "${INTEN_LABEL}" ]]; then
                    HAS_INTEN=1
                    break
                fi
            done

            FUNC_RANGE_ARG=()
            if [[ "${HAS_INTEN}" -eq 1 ]]; then
                SUBBRICKS_ARG=(-set_subbricks -1 "${INTEN_LABEL}" "${STAT_LABEL}")
                FUNC_RANGE_ARG=(-func_range 3)
            else
                # Fallback: Use stat for both
                SUBBRICKS_ARG=(-set_subbricks -1 "${STAT_LABEL}" "${STAT_LABEL}")
            fi

            SAFE_NAME=$(echo "${INTEN_LABEL}" | tr ' :/#+[]' '______')
            if [[ -z "${SAFE_NAME}" ]]; then
                SAFE_NAME=$(echo "${STAT_LABEL}" | tr ' :/#+[]' '______')
            fi

            log_info "Generating image for: ${SAFE_NAME} (${STAT_LABEL})"

            set +e # Don't exit on single image failure
            @chauffeur_afni \
                -ulay               "${MNI_TEMPLATE}" \
                -ulay_range         0% 130% \
                -olay               "${OUTPUT_PREFIX}+tlrc" \
                -box_focus_slices   AMASK_FOCUS_ULAY \
                ${FUNC_RANGE_ARG[@]+"${FUNC_RANGE_ARG[@]}"} \
                -cbar               Reds_and_Blues_Inv \
                -thr_olay_p2stat    0.005 \
                -thr_olay_pside     bisided \
                -olay_alpha         Yes \
                -olay_boxed         Yes \
                "${SUBBRICKS_ARG[@]}" \
                -opacity            5 \
                -zerocolor          white \
                -label_color        black \
                -set_dicom_xyz      -20 -8 -16 \
                -delta_slices       6 15 10 \
                -clusterize         "-NN 2 -clust_nvox 35" \
                -prefix             "${CHAUFFEUR_DIR}/${SAFE_NAME}" \
                -set_xhairs         OFF \
                -label_mode         1 \
                -label_size         3 \
                -montx 3 -monty 3 \
                -do_clean
            set -euo pipefail
        fi
    done
else
    log_warn "Output dataset ${OUTPUT_PREFIX}+tlrc.HEAD not found."
fi

log_success "Script Finished"
