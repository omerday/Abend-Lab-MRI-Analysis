#!/bin/bash

OPTIND=1

# Define the short and long options
short_options="hs:i:l:"
long_options="help,session:,subject:,input:,lag:,lag_block_1:,lag_block_2:"
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
lag_block_1=0
lag_block_2=0
input_folder=""
session=1
subj=""

while true; do
  case ${1} in
    -h|--help)
        echo "Usage: $0 [-h help] [-s session] [-i input folder] [-lag seconds] [--subject subject ID]"
        echo
        echo "Options:"
        echo "  -h, --help      Show this help message and exit."
        echo "  -i, --input     Specify the location of the input."
        echo "  -s, --session   Specify the session number."
        echo "  --subjects      Specify a comma-separated list of subject IDs."
        echo "  -l,--lag        Specify an amount of time to subtract from all timing files."
        echo "  --lag_block_1   specify an amount of time to subtract from block 1 timing file. This will override -l."
        echo "  --lag_block_2   specify an amount of time to subtract from block 2 timing file. This will override -l."
        echo
        echo "Example:"
        echo "  $0 -s 2 --subject sub-01 --lag_block_1 23 --input /path/to/input"
        exit 1
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
    --lag_block_1)
        lag_block_1=$2
        shift 2
        ;;
    --lag_block_2)
        lag_block_2=$2
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

cd ${input_folder}/${subj}/ses-${session}/func
if [ -d "./timings" ]; then
    rm -r ./timings
fi
mkdir timings

if [ $lag_block_1 -eq 0 ]; then
    lag_block_1=$lag
fi

if [ $lag_block_2 -eq 0 ]; then
    lag_block_2=$lag
fi

cat ${subj}_ses-${session}_task-war_run-1_events.tsv | awk -v lag_val="${lag_block_1}" '{if ($2==31 || $2==32 || $2==33 || $2==34) {print $1 - lag_val, $4, 1}}' > timings/negative_image_run1.txt
cat ${subj}_ses-${session}_task-war_run-1_events.tsv | awk -v lag_val="${lag_block_1}" '{if ($2=="71" || $2=="72" || $2=="73" || $2=="74") {print $1 - lag_val, $4, 1}}' > timings/positive_image_run1.txt
cat ${subj}_ses-${session}_task-war_run-1_events.tsv | awk -v lag_val="${lag_block_1}" '{if ($2=="51" || $2=="52" || $2=="53" || $2=="54") {print $1 - lag_val, $4, 1}}' > timings/neutral_image_run1.txt
cat ${subj}_ses-${session}_task-war_run-1_events.tsv | awk -v lag_val="${lag_block_1}" '{if ($2=="31") {print $1 - lag_val, 22, 1}}' > timings/negative_block_run1.txt
cat ${subj}_ses-${session}_task-war_run-1_events.tsv | awk -v lag_val="${lag_block_1}" '{if ($2=="71") {print $1 - lag_val, 22, 1}}' > timings/positive_block_run1.txt
cat ${subj}_ses-${session}_task-war_run-1_events.tsv | awk -v lag_val="${lag_block_1}" '{if ($2=="51") {print $1 - lag_val, 22, 1}}' > timings/neutral_block_run1.txt
cat ${subj}_ses-${session}_task-war_run-1_events.tsv | awk -v lag_val="${lag_block_1}" '{if ($2=="22" || $2=="24") {print $1 - lag_val, $4, 1}}' > timings/rest_run1.txt

cat ${subj}_ses-${session}_task-war_run-2_events.tsv | awk -v lag_val="${lag_block_2}" '{if ($2=="31" || $2=="32" || $2=="33" || $2=="34") {print $1 - lag_val, $4, 1}}' > timings/negative_image_run2.txt
cat ${subj}_ses-${session}_task-war_run-2_events.tsv | awk -v lag_val="${lag_block_2}" '{if ($2=="71" || $2=="72" || $2=="73" || $2=="74") {print $1 - lag_val, $4, 1}}' > timings/positive_image_run2.txt
cat ${subj}_ses-${session}_task-war_run-2_events.tsv | awk -v lag_val="${lag_block_2}" '{if ($2=="51" || $2=="52" || $2=="53" || $2=="54") {print $1 - lag_val, $4, 1}}' > timings/neutral_image_run2.txt
cat ${subj}_ses-${session}_task-war_run-2_events.tsv | awk -v lag_val="${lag_block_2}" '{if ($2=="31") {print $1 - lag_val, 22, 1}}' > timings/negative_block_run2.txt
cat ${subj}_ses-${session}_task-war_run-2_events.tsv | awk -v lag_val="${lag_block_2}" '{if ($2=="71") {print $1 - lag_val, 22, 1}}' > timings/positive_block_run2.txt
cat ${subj}_ses-${session}_task-war_run-2_events.tsv | awk -v lag_val="${lag_block_2}" '{if ($2=="51") {print $1 - lag_val, 22, 1}}' > timings/neutral_block_run2.txt
cat ${subj}_ses-${session}_task-war_run-2_events.tsv | awk -v lag_val="${lag_block_2}" '{if ($2=="22" || $2=="24") {print $1 - lag_val, $4, 1}}' > timings/rest_run2.txt

#Now convert to AFNI format
cd timings
timing_tool.py -fsl_timing_files negative_image*.txt -write_timing negative_image.1D
timing_tool.py -fsl_timing_files positive_image*.txt -write_timing positive_image.1D
timing_tool.py -fsl_timing_files neutral_image*.txt -write_timing neutral_image.1D
timing_tool.py -fsl_timing_files negative_block*.txt -write_timing negative_block.1D
timing_tool.py -fsl_timing_files positive_block*.txt -write_timing positive_block.1D
timing_tool.py -fsl_timing_files neutral_block*.txt -write_timing neutral_block.1D
timing_tool.py -fsl_timing_files rest*.txt -write_timing rest.1D

cd ../../..
