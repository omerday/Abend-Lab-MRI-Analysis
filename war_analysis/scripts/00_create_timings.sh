#!/bin/bash

# --- Script: 00_create_timings.sh ---
# Description: Converts event .tsv files into AFNI-compatible .1D timing files for the WAR task.

set -e # Exit immediately if a command exits with a non-zero status.

# Get the directory where the script is located
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Default values
SUBJECT=""
SESSION="1"
INPUT_DIR=""
LAG_BLOCK_1=0
LAG_BLOCK_2=0

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --subject) SUBJECT="$2"; shift 2;;
        --session) SESSION="$2"; shift 2;;
        --input) INPUT_DIR="$2"; shift 2;;
        --lag_block_1) LAG_BLOCK_1="$2"; shift 2;;
        --lag_block_2) LAG_BLOCK_2="$2"; shift 2;;
        *) echo "Unknown option: $1" >&2; exit 1;;
    esac
done

# Validate required arguments
if [ -z "$SUBJECT" ] || [ -z "$SESSION" ] || [ -z "$INPUT_DIR" ]; then
    echo "Usage: $0 --subject <ID> --session <N> --input <dir> [--lag_block_1 <N>] [--lag_block_2 <N>]" >&2
    exit 1
fi

SESSION_PREFIX="ses-${SESSION}"
FUNC_DIR="${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func"

echo "--- Starting Onset Conversion for ${SUBJECT}, ${SESSION_PREFIX} ---"
echo "--- Lag Block 1: ${LAG_BLOCK_1} seconds ---"
echo "--- Lag Block 2: ${LAG_BLOCK_2} seconds ---"

if [ ! -d "$FUNC_DIR" ]; then
    echo "Error: Func directory not found at ${FUNC_DIR}" >&2
    exit 1
fi

cd "$FUNC_DIR"
if [ -d "./timings" ]; then
    echo "Removing existing timings directory."
    rm -r ./timings
fi
mkdir timings

# --- Run 1 ---
TSV_FILE_1="${SUBJECT}_${SESSION_PREFIX}_task-war_run-1_events.tsv"
if [ -f "$TSV_FILE_1" ]; then
    awk -v lag_val="${LAG_BLOCK_1}" '{if ($2==31 || $2==32 || $2==33 || $2==34) {print $1 - lag_val, 4, 1}}' "$TSV_FILE_1" > timings/negative_image_run1.txt
    awk -v lag_val="${LAG_BLOCK_1}" '{if ($2=="71" || $2=="72" || $2=="73" || $2=="74") {print $1 - lag_val, 4, 1}}' "$TSV_FILE_1" > timings/positive_image_run1.txt
    awk -v lag_val="${LAG_BLOCK_1}" '{if ($2=="51" || $2=="52" || $2=="53" || $2=="54") {print $1 - lag_val, 4, 1}}' "$TSV_FILE_1" > timings/neutral_image_run1.txt
    awk -v lag_val="${LAG_BLOCK_1}" '{if ($2=="31") {print $1 - lag_val, 22, 1}}' "$TSV_FILE_1" > timings/negative_block_run1.txt
    awk -v lag_val="${LAG_BLOCK_1}" '{if ($2=="71") {print $1 - lag_val, 22, 1}}' "$TSV_FILE_1" > timings/positive_block_run1.txt
    awk -v lag_val="${LAG_BLOCK_1}" '{if ($2=="51") {print $1 - lag_val, 22, 1}}' "$TSV_FILE_1" > timings/neutral_block_run1.txt
    awk -v lag_val="${LAG_BLOCK_1}" '{if ($2=="22" || $2=="24") {print $1 - lag_val, $4, 1}}' "$TSV_FILE_1" > timings/rest_run1.txt
else
    echo "Warning: Run 1 event file not found: ${TSV_FILE_1}"
fi

# --- Run 2 ---
TSV_FILE_2="${SUBJECT}_${SESSION_PREFIX}_task-war_run-2_events.tsv"
if [ -f "$TSV_FILE_2" ]; then
    awk -v lag_val="${LAG_BLOCK_2}" '{if ($2=="31" || $2=="32" || $2=="33" || $2=="34") {print $1 - lag_val, 4, 1}}' "$TSV_FILE_2" > timings/negative_image_run2.txt
    awk -v lag_val="${LAG_BLOCK_2}" '{if ($2=="71" || $2=="72" || $2=="73" || $2=="74") {print $1 - lag_val, 4, 1}}' "$TSV_FILE_2" > timings/positive_image_run2.txt
    awk -v lag_val="${LAG_BLOCK_2}" '{if ($2=="51" || $2=="52" || $2=="53" || $2=="54") {print $1 - lag_val, 4, 1}}' "$TSV_FILE_2" > timings/neutral_image_run2.txt
    awk -v lag_val="${LAG_BLOCK_2}" '{if ($2=="31") {print $1 - lag_val, 22, 1}}' "$TSV_FILE_2" > timings/negative_block_run2.txt
    awk -v lag_val="${LAG_BLOCK_2}" '{if ($2=="71") {print $1 - lag_val, 22, 1}}' "$TSV_FILE_2" > timings/positive_block_run2.txt
    awk -v lag_val="${LAG_BLOCK_2}" '{if ($2=="51") {print $1 - lag_val, 22, 1}}' "$TSV_FILE_2" > timings/neutral_block_run2.txt
    awk -v lag_val="${LAG_BLOCK_2}" '{if ($2=="22" || $2=="24") {print $1 - lag_val, $4, 1}}' "$TSV_FILE_2" > timings/rest_run2.txt
else
    echo "Warning: Run 2 event file not found: ${TSV_FILE_2}"
fi

# --- SCR Binned Files ---
if [ -f "binned_scr_run-1.txt" ]; then
    python "${SCRIPT_DIR}/../utils/create_tr_magnitude_file.py" --binned_tsv binned_scr_run-1.txt --lag "${LAG_BLOCK_1}" --output timings/scr_binned_run-1.1D
fi
if [ -f "binned_scr_run-2.txt" ]; then
    python "${SCRIPT_DIR}/../utils/create_tr_magnitude_file.py" --binned_tsv binned_scr_run-2.txt --lag "${LAG_BLOCK_2}" --output timings/scr_binned_run-2.1D
fi

# --- Convert to AFNI format ---
cd timings
timing_tool.py -fsl_timing_files negative_image*.txt -write_timing negative_image.1D
timing_tool.py -fsl_timing_files positive_image*.txt -write_timing positive_image.1D
timing_tool.py -fsl_timing_files neutral_image*.txt -write_timing neutral_image.1D
timing_tool.py -fsl_timing_files negative_block*.txt -write_timing negative_block.1D
timing_tool.py -fsl_timing_files positive_block*.txt -write_timing positive_block.1D
timing_tool.py -fsl_timing_files neutral_block*.txt -write_timing neutral_block.1D
timing_tool.py -fsl_timing_files rest*.txt -write_timing rest.1D

# Concatenate binned SCR files if they exist
if [ -f "scr_binned_run-1.1D" ] || [ -f "scr_binned_run-2.1D" ]; then
    cat scr_binned_run-*.1D > scr_binned.1D
fi

echo "--- Onset Conversion for ${SUBJECT} Complete ---"
