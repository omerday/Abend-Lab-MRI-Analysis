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
parsed=$(getopt -o "$short_options" -l "$long_options" -- "$@")

# Check if getopt was successful
if [ $? -ne 0 ]; then
  echo "Error parsing options." >&2
  exit 1
fi

# Set the positional parameters to the parsed options and arguments
eval set -- "$parsed"

input_folder=""
subject_ids=()

# Loop through the options
while true; do
  case ${1} in
    -h|--help)
      echo "Usage: $0 [-i input_folder] --subjects <sub1,sub2,...> sub-??*"
      echo
      echo "Options:"
      echo "  -h, --help      Show this help message and exit."
      echo "  -i, --input     Specify the location of the input."
      echo "  --subjects       Specify a comma-separated list of subject IDs."
      echo
      echo "Example:"
      echo "  $0 --subjects sub-01,sub-03,sub-05 --input /path/to/input"
      exit 1
      ;;
    --subjects)
        IFS=',' read -ra subject_ids+=$2 # Append the subject ID to the array
        echo "++Subject IDs: ${subject_ids[@]}"
        shift 2
        ;;
    -i|--input)
        input_folder=$2
        echo "++Input folder: ${input_folder}"
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

echo "subjects - ${subject_ids}"

if [ ${#subject_ids[@]} -eq 0 ]; then
    echo "No subjects provided"
    exit 1
fi

if [ ! -d logs ]; then
    mkdir logs
fi

dataTable="subj session stimulus    InputFile"
echo $dataTable
