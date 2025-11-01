#!/bin/bash

echo "Starting group analysis script for MDMA patients before and after the treatment."
echo "Please note, this script should only be run with bash"
echo "====================================================="
echo ""

OPTIND=1

# Define the short and long options
short_options="hs:i:"
long_options="help,subjects:,input:"

# Parse the options using getopt
# The `getopt` command rearranges arguments and handles options.
# `set -- "$parsed"` is used to re-evaluate the command line arguments
# based on the output of `getopt`.
parsed=$(getopt -o "$short_options" -l "$long_options" -- "$@")

# Check if getopt was successful
if [ $? -ne 0 ]; then
  echo "Error parsing options. Please check your arguments." >&2
  exit 1
fi

# Set the positional parameters to the parsed options and arguments
# This is crucial for the while loop to correctly process the arguments
eval set -- "$parsed"

input_folder=""
subject_ids=() # Initialize an empty array for subject IDs
sessions=("ses-1", "ses-2")
stimuli=("neg", "pos", "neut")
mask_epi_anat_files=""

# Loop through the options
while true; do
  case "${1}" in # Use quotes around $1 to prevent issues with spaces
    -h|--help)
      echo "Usage: $0 [-i input_folder] --subjects <sub1,sub2,...> sub-??*"
      echo
      echo "Options:"
      echo "  -h, --help      Show this help message and exit."
      echo "  -i, --input     Specify the location of the input."
      echo "  --subjects      Specify a comma-separated list of subject IDs."
      echo
      echo "Example:"
      echo "  $0 --subjects sub-01,sub-03,sub-05 --input /path/to/input"
      exit 0 # Exit with 0 for help message
      ;;
    --subjects)
        # Read the comma-separated string ($2) into a temporary array
        # `read -r -a` reads into an array, `-r` prevents backslash escapes.
        # `<<< "$2"` is a here string, passing the value of $2 as input to read.
        IFS=',' read -r -a temp_subject_ids <<< "$2"
        # Append all elements from the temporary array to the main subject_ids array
        # The `"${array_name[@]}"` syntax expands all elements of the array.
        subject_ids+=("${temp_subject_ids[@]}")
        echo "++Subject IDs: ${subject_ids[@]}" # Print all elements for debugging
        shift 2 # Shift past the option (`--subjects`) and its argument (`$2`)
        ;;
    -i|--input)
        input_folder="$2" # Assign the argument to input_folder
        echo "++Input folder: ${input_folder}"
        shift 2 # Shift past the option (`-i` or `--input`) and its argument (`$2`)
        ;;
    --) 
      shift # Shift past the `--`
      break # Exit the loop
      ;;
    *)
      echo "Unknown option or argument: $1" >&2
      exit 1
      ;;
  esac
done

# Print all collected subject IDs
echo "Subjects collected: ${subject_ids[@]}"

if [ ${#subject_ids[@]} -eq 0 ]; then
    echo "No subjects provided"
    exit 1
fi

if [ ! -d logs ]; then
    mkdir logs
fi

data_table="subj session stimulus    InputFile"

for subject in ${subject_ids[@]}; do
    for session in ${sessions[@]}; do
        mask_epi_anat_files="${mask_epi_anat_files} ${input}/${subject}.${session}.results/mask_epi_anat.*+tlrc.HEAD"
        for stimulus in ${stimuli[@]}; do
            data_table+="\n${subject}    ${session}  ${stimulus} ${input_folder}/${subject}.${session}.results/stats.${subject}+tlrc[${stimulus}-blck_GLT#0_Coef]"
        done
    done
done

if [ -f "group_mask_olap.7.tlrc" ]; then
    rm group_mask_olap.7.tlrc
fi

3dmask_tool -input ${mask_epi_anat_files} \
    -prefix group_mask_olap.7 \
    -frac 0.7

3dLMEr -prefix LME_MDMA_Within_Subject \
    -mask group_mask_olap.7.tlrc \
    -bounds -2 2  \
    -SS_type 3 \
    -model 'session*stimulus+(1|subj)+(1|session:subj)+(1|stimulus:subj)' \
    -gltCode neg.cng    'session : 1*"ses-2" -1*"ses-1" stimulus : 1*neg' \
    -gltCode pos.cng    'session : 1*"ses-2" -1*"ses-1" stimulus : 1*pos' \
    -gltCode neut.cng    'session : 1*"ses-2" -1*"ses-1" stimulus : 1*neut' \
    -gltCode neg.pos.diff 'session : 1*"ses-2" -1*"ses-1" stimulus : 1*neg -1*pos' \
    -gltCode neg.neut.diff 'session : 1*"ses-2" -1*"ses-1" stimulus : 1*neg -1*neut' \
    -gltCode pos.neut.diff 'session : 1*"ses-2" -1*"ses-1" stimulus : 1*pos -1*neut' \
    -dataTable ${data_table}