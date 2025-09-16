
#!/bin/bash

# --- Script: 00_create_timings.sh ---
# Description: Converts event .tsv files into AFNI-compatible .1D timing files.
# Date: 2025-09-16

set -e # Exit immediately if a command exits with a non-zero status.

# Default values
SUBJECT=""
SESSION="1"
INPUT_DIR=""
RUNS=5
LAG=0

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --subject)
            SUBJECT="$2"
            shift 2
            ;;
        --session)
            SESSION="$2"
            shift 2
            ;;
        --input)
            INPUT_DIR="$2"
            shift 2
            ;;
        --runs)
            RUNS="$2"
            shift 2
            ;;
        --lag)
            LAG="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$SUBJECT" ] || [ -z "$SESSION" ] || [ -z "$INPUT_DIR" ]; then
    echo "Usage: $0 --subject <ID> --session <N> --input <dir> [--runs <N>] [--lag <N>]" >&2
    exit 1
fi

SESSION_PREFIX="ses-${SESSION}"
FUNC_DIR="${INPUT_DIR}/${SUBJECT}/${SESSION_PREFIX}/func"

echo "--- Starting Onset Conversion for ${SUBJECT}, ${SESSION_PREFIX} ---"

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

for i in $(seq 1 $RUNS); do
    TSV_FILE="${SUBJECT}_${SESSION_PREFIX}_task-tim_run-${i}_events.tsv"
    if [ ! -f "$TSV_FILE" ]; then
        echo "Warning: Event file not found, skipping: ${TSV_FILE}"
        continue
    fi

    # Timed events - square onset
    awk -v lag_val="$LAG" '{if ($3=="21") {print $1 - lag_val, $2, 1}}' "$TSV_FILE" > timings/green_square_onset_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="41") {print $1 - lag_val, $2, 1}}' "$TSV_FILE" > timings/yellow_square_onset_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="81") {print $1 - lag_val, $2, 1}}' "$TSV_FILE" > timings/red_square_onset_run${i}.txt

    # Amplitude events - square onset
    awk -v lag_val="$LAG" '{if ($3=="21") {printf $1 - lag_val"*2 "}}' "$TSV_FILE" >> timings/amp_square_onset_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="41") {printf $1 - lag_val"*6 "}}' "$TSV_FILE" >> timings/amp_square_onset_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="81") {printf $1 - lag_val"*8 "}}' "$TSV_FILE" >> timings/amp_square_onset_run${i}.txt
    echo `cat timings/amp_square_onset_run${i}.txt` >> timings/amp_square_onset.1D

    # Timed events - pre heat
    awk -v lag_val="$LAG" '{if ($3=="25") {print $1 - lag_val, $2, 1}}' "$TSV_FILE" > timings/low_temp_pre_pain_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="45") {print $1 - lag_val, $2, 1}}' "$TSV_FILE" > timings/med_temp_pre_pain_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="85") {print $1 - lag_val, $2, 1}}' "$TSV_FILE" > timings/high_temp_pre_pain_run${i}.txt

    # Amplitude events - pre heat
    awk -v lag_val="$LAG" '{if ($3=="25") {printf $1 - lag_val"*2 "}}' "$TSV_FILE" >> timings/amp_pre_pain_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="45") {printf $1 - lag_val"*6 "}}' "$TSV_FILE" >> timings/amp_pre_pain_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="85") {printf $1 - lag_val"*8 "}}' "$TSV_FILE" >> timings/amp_pre_pain_run${i}.txt
    echo `cat timings/amp_pre_pain_run${i}.txt` >> timings/amp_pre_pain.1D

    # Timed events - heat
    awk -v lag_val="$LAG" '{if ($3=="26") {print $1 - lag_val, $2, 1}}' "$TSV_FILE" > timings/low_temp_pain_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="46") {print $1 - lag_val, $2, 1}}' "$TSV_FILE" > timings/med_temp_pain_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="86") {print $1 - lag_val, $2, 1}}' "$TSV_FILE" > timings/high_temp_pain_run${i}.txt

    # Amplitude events - heat
    awk -v lag_val="$LAG" '{if ($3=="26") {printf $1 - lag_val"*2 "}}' "$TSV_FILE" >> timings/amp_pain_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="46") {printf $1 - lag_val"*6 "}}' "$TSV_FILE" >> timings/amp_pain_run${i}.txt
    awk -v lag_val="$LAG" '{if ($3=="86") {printf $1 - lag_val"*8 "}}' "$TSV_FILE" >> timings/amp_pain_run${i}.txt
    echo `cat timings/amp_pain_run${i}.txt` >> timings/amp_pain.1D

    # SCR and Rating amplitude files
    # These source files (e.g., anticipation_scr_amplitude_run-i.txt) are assumed to exist.
    [ -f anticipation_scr_amplitude_run-${i}.txt ] && awk -v lag_val="$LAG" '{print $2 - lag_val"*"$3}' anticipation_scr_amplitude_run-${i}.txt > timings/anticipation_scr_amp_run-${i}.txt
    [ -f timings/anticipation_scr_amp_run-${i}.txt ] && echo `cat timings/anticipation_scr_amp_run-${i}.txt` >> timings/anticipation_scr_amp.1D

    [ -f anticipation_scr_amplitude_run-${i}.txt ] && awk -v lag_val="$LAG" '{print ($2 - lag_val) "*" ($1 % 10)}' anticipation_scr_amplitude_run-${i}.txt > timings/anticipation_1234_amp_run-${i}.txt
    [ -f timings/anticipation_1234_amp_run-${i}.txt ] && echo `cat timings/anticipation_1234_amp_run-${i}.txt` >> timings/anticipation_1234_amp.1D

    [ -f pain_scr_amplitude_run-${i}.txt ] && awk -v lag_val="$LAG" '{print $2 - lag_val"*"$3}' pain_scr_amplitude_run-${i}.txt > timings/pain_scr_amp_run-${i}.txt
    [ -f timings/pain_scr_amp_run-${i}.txt ] && echo `cat timings/pain_scr_amp_run-${i}.txt` >> timings/pain_scr_amp.1D

    [ -f pain_scr_amplitude_run-${i}.txt ] && awk -v lag_val="$LAG" '{print $2 - lag_val"*"$4}' pain_scr_amplitude_run-${i}.txt > timings/pain_rating_amp_run-${i}.txt
    [ -f timings/pain_rating_amp_run-${i}.txt ] && echo `cat timings/pain_rating_amp_run-${i}.txt` >> timings/pain_rating_amp.1D
done

# Now convert to AFNI format using timing_tool.py
cd timings
timing_tool.py -fsl_timing_files low_temp_pre_pain*.txt -write_timing low_temp_pre_pain.1D -overwrite
timing_tool.py -fsl_timing_files med_temp_pre_pain*.txt -write_timing med_temp_pre_pain.1D -overwrite
timing_tool.py -fsl_timing_files high_temp_pre_pain*.txt -write_timing high_temp_pre_pain.1D -overwrite

timing_tool.py -fsl_timing_files green_square_onset*.txt -write_timing green_square_onset.1D -overwrite
timing_tool.py -fsl_timing_files yellow_square_onset*.txt -write_timing yellow_square_onset.1D -overwrite
timing_tool.py -fsl_timing_files red_square_onset*.txt -write_timing red_square_onset.1D -overwrite

echo "--- Onset Conversion for ${SUBJECT} Complete ---"
