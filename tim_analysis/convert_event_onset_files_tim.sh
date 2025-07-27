#!/bin/bash

OPTIND=1

# Define the short and long options
short_options="hs:r:i:l:"
long_options="help,session:,runs:,subject:,input:,lag:"
# Parse the options using getopt
parsed=$(getopt -o "$short_options" -l "$long_options" -- "$@")

# Check if getopt was successful
if [ $? -ne 0 ]; then
  echo "Error parsing options." >&2
  exit 1
fi

# Set the positional parameters to the parsed options and arguments
eval set -- "$parsed"

lag=0
input_folder=""
session=1
runs=5
subj=""

while true; do
  case ${1} in
    -h|--help)
        echo "Usage: $0 [-h help] [-r runs] [-s session] [-i input folder] [--subject subject ID]"
        echo
        echo "Options:"
        echo "  -h, --help      Show this help message and exit."
        echo "  -i, --input     Specify the location of the input."
        echo "  -s, --session   Specify the session number."
        echo "  -r, --runs      Specify the amount of runs performed in the session."
        echo "  --subject       Specify a comma-separated list of subject IDs."
        echo
        echo "Example:"
        echo "  $0 -s 2 --subject sub-01 --input /path/to/input"
        exit 1
        ;;
    -r|--runs)
        runs=$2
        shift 2
        ;;
    -s|--session)
        session=$2
        shift 2
        ;;
    -i|--input)
        input_folder=$2
        shift 2
        ;;
    -l|--lag)
        lag=$2
        shift 2
        ;;
    --subject)
        subj=$2
        shift 2
        ;;
    --)
        shift
        break
        ;;
    *)
        echo "Unknown option: $1" >&2
        exit 1
        ;;
    esac
done

echo "Starting onset conversion for subject ${subj}"
echo "Number of runs - ${runs}"
echo "Lag provided - ${lag}"

cd ${input_folder}/${subj}/ses-${session}/func
if [ -d "./timings" ]; then
    rm -r ./timings
fi
mkdir timings

for i in $(seq 1 $runs); do
    # Timed events - square onset
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="21") {print $1 - lag_val, $2, 1}}' > timings/green_square_onset_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="41") {print $1 - lag_val, $2, 1}}' > timings/yellow_square_onset_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="81") {print $1 - lag_val, $2, 1}}' > timings/red_square_onset_run${i}.txt

    # Amplitude events - square onset
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="21") {printf $1 - lag_val"*2 "}}' >> timings/amp_square_onset_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="41") {printf $1 - lag_val"*6 "}}' >> timings/amp_square_onset_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="81") {printf $1 - lag_val"*8 "}}' >> timings/amp_square_onset_run${i}.txt

    echo `cat timings/amp_square_onset_run${i}.txt` >> timings/amp_square_onset.1D

    # Timed events - pre heat
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="25") {print $1 - lag_val, $2, 1}}' > timings/low_temp_pre_pain_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="45") {print $1 - lag_val, $2, 1}}' > timings/med_temp_pre_pain_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="85") {print $1 - lag_val, $2, 1}}' > timings/high_temp_pre_pain_run${i}.txt

    # Amplitude events - pre heat
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="25") {printf $1 - lag_val"*2 "}}' >> timings/amp_pre_pain_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="45") {printf $1 - lag_val"*6 "}}' >> timings/amp_pre_pain_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="85") {printf $1 - lag_val"*8 "}}' >> timings/amp_pre_pain_run${i}.txt

    echo `cat timings/amp_pre_pain_run${i}.txt` >> timings/amp_pre_pain.1D

    # Timed events - heat
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="26") {print $1 - lag_val, $2, 1}}' > timings/low_temp_pain_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="46") {print $1 - lag_val, $2, 1}}' > timings/med_temp_pain_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="86") {print $1 - lag_val, $2, 1}}' > timings/high_temp_pain_run${i}.txt

    # Amplitude events - heat
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="26") {printf $1 - lag_val"*2 "}}' >> timings/amp_pain_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="46") {printf $1 - lag_val"*6 "}}' >> timings/amp_pain_run${i}.txt
    cat ${subj}_ses-${session}_task-tim_run-${i}_events.tsv | awk -v lag_val="$lag" '{if ($3=="86") {printf $1 - lag_val"*8 "}}' >> timings/amp_pain_run${i}.txt

    echo `cat timings/amp_pain_run${i}.txt` >> timings/amp_pain.1D

    cat scr_amplitude_run-${i}.txt | awk -v lag_val="$lag" '{print $2 - lag_val"*"$3}' > timings/scr_amp_run-${i}.txt
    echo `cat timings/scr_amp_run-${i}.txt` >> scr_amp.1D
done

#Now convert to AFNI format
cd timings
timing_tool.py -fsl_timing_files low_temp_pre_pain*.txt -write_timing low_temp_pre_pain.1D
timing_tool.py -fsl_timing_files med_temp_pre_pain*.txt -write_timing med_temp_pre_pain.1D
timing_tool.py -fsl_timing_files high_temp_pre_pain*.txt -write_timing high_temp_pre_pain.1D

timing_tool.py -fsl_timing_files green_square_onset*.txt -write_timing green_square_onset.1D
timing_tool.py -fsl_timing_files yellow_square_onset*.txt -write_timing yellow_square_onset.1D
timing_tool.py -fsl_timing_files red_square_onset*.txt -write_timing red_square_onset.1D

cd ../../..