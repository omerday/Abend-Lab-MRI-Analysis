#!/bin/bash

echo "Starting group analysis script for TIM fMRI."
echo "Please note, this script should only be run with bash"
echo "====================================================="
echo ""

OPTIND=1

# Define the short and long options
short_options="h"
long_options="help,input:,subjects:"

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
subject_ids=()
mask_epi_anat_files=""

# Loop through the options
while true; do
  case "${1}" in # Use quotes around $1 to prevent issues with spaces
    -h|--help)
      echo "Usage: $0 --subjects sub-??* --input /path/to/input"
      echo
      echo "Options:"
      echo "  -h, --help        Show this help message and exit."
      echo "  --subjects        List all subjects, comma-seperated"
      echo "  --input           Path to the single-subject analysed data folder"
      echo
      echo "Example:"
      echo "  $0 --subjects sub-01,sub-03,sub-05 --input /path/to/input"
      exit 0 # Exit with 0 for help message
      ;;
    --subjects)
        # Read the comma-separated string ($2) into a temporary array
        # `read -r -a` reads into an array, `-r` prevents backslash escapes.
        # `<<< "$2"` is a here string, passing the value of $2 as input to read.
        IFS=',' read -r -a subject_ids <<< "$2"
        shift 2 # Shift past the option (`--subjects`) and its argument (`$2`)
        ;;
    --input)
        input_folder="$2" 
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
echo "ubjects collected: ${subject_ids[@]}"

if [ ${#subject_ids[@]} -eq 0 ]; then
    echo "No subjects provided"
    exit 1
fi

if [ ! -d logs ]; then
    mkdir logs
fi

dsets=""
for subject in ${subject_ids[@]}; do
    mask_epi_anat_files="${mask_epi_anat_files} ${input_folder}/${subject}.ses-1.antic.1234.results/mask_epi_anat.*+tlrc.HEAD"
    dsets="${dsets} ${subject} ${input_folder}/${subject}.ses-1.antic.1234.results/stats.${subject}+tlrc[SCR#1_Coef]"
done

if [ -f "group_mask_olap.4+tlrc.HEAD" ]; then
    rm group_mask_olap.4+tlrc.HEAD
fi

if [ -f "group_mask_olap.4+tlrc.BRIK.gz" ]; then
    rm group_mask_olap.4+tlrc.BRIK.gz
fi

3dmask_tool -input ${mask_epi_anat_files} \
    -prefix group_mask_olap.4 \
    -frac 0.4

3dttest++ -prefix 3dttest_TIM_fMRI_ANTIC_1234_SCR \
    -setA SCR#1 ${dsets}

3dcalc  -a 3dttest_TIM_fMRI_ANTIC_1234_SCR+tlrc.HEAD \
        -b group_mask_olap.4+tlrc.HEAD \
        -expr 'a*b' \
        -prefix 3dttest_TIM_fMRI_ANTIC_1234_SCR_masked

if [ ! -d chauffeur ]; then
    mkdir chauffeur
fi

@chauffeur_afni                                                         \
    -ulay               MNI152_2009_template.nii.gz                     \
    -ulay_range         0% 130%                                         \
    -olay               ./3dttest_TIM_fMRI_ANTIC_1234_SCR_masked+tlrc.HEAD    \
    -box_focus_slices   AMASK_FOCUS_ULAY                                \
    -func_range         3                                               \
    -cbar               Reds_and_Blues_Inv                              \
    -thr_olay_p2stat    0.1                                            \
    -thr_olay_pside     bisided                                         \
    -olay_alpha         Yes                                             \
    -olay_boxed         Yes                                             \
    -set_subbricks      -1 "SCR#1_Tstat" "SCR#1_Tstat"              \
    -opacity            5                                               \
    -zerocolor          white                                           \
    -prefix             chauffeur/ANTIC/1234                 \
    -clusterize        "-NN 2 -clust_nvox 20"               \
    -set_xhairs         OFF                                             \
    -set_dicom_xyz      -20 -8 -16                                         \
    -delta_slices       6 15 10                                         \
    -label_color        black                                           \
    -montx 3 -monty 3                                                   \
    -label_mode 1 -label_size 4
