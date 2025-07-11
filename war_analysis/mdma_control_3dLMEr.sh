#!/bin/bash

echo "Starting group analysis script for MDMA patients against control group."
echo "Please note, this script should only be run with bash"
echo "====================================================="
echo ""

OPTIND=1

# Define the short and long options
short_options="h"
long_options="help,md_subjects:,md_path:,control_subjects:,control_path:"

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

mdma_input_folder=""
mdma_subject_ids=()
control_input_folder=""
control_subject_ids=()
stimuli=("neg" "pos" "neut")
mask_epi_anat_files=""

# Loop through the options
while true; do
  case "${1}" in # Use quotes around $1 to prevent issues with spaces
    -h|--help)
      echo "Usage: $0 --md_subjects <sub1,sub2,...> sub-??* --md_path /path/to/md/patients --control_subjects <sub1,sub2,...> sub-??* --control_path /path/to/control/patients"
      echo
      echo "Options:"
      echo "  -h, --help      Show this help message and exit."
      echo "  --md_subjects   List all subjects in MD group, comma-seperated"
      echo "  --md_path       Path to the single-subject analysed data folder for the MD group"
      echo "  --control_subjects   List all subjects in Control group, comma-seperated"
      echo "  --control_path       Path to the single-subject analysed data folder for the Control group"
      echo
      echo "Example:"
      echo "  $0 --subjects sub-01,sub-03,sub-05 --input /path/to/input"
      exit 0 # Exit with 0 for help message
      ;;
    --md_subjects)
        # Read the comma-separated string ($2) into a temporary array
        # `read -r -a` reads into an array, `-r` prevents backslash escapes.
        # `<<< "$2"` is a here string, passing the value of $2 as input to read.
        IFS=',' read -r -a mdma_subject_ids <<< "$2"
        shift 2 # Shift past the option (`--subjects`) and its argument (`$2`)
        ;;
    --md_path)
        mdma_input_folder="$2" 
        echo "++Input folder: ${mdma_input_folder}"
        shift 2 # Shift past the option (`-i` or `--input`) and its argument (`$2`)
        ;;
    --control_subjects)
        # Read the comma-separated string ($2) into a temporary array
        # `read -r -a` reads into an array, `-r` prevents backslash escapes.
        # `<<< "$2"` is a here string, passing the value of $2 as input to read.
        IFS=',' read -r -a control_subject_ids <<< "$2"
        shift 2 # Shift past the option (`--subjects`) and its argument (`$2`)
        ;;
    --control_path)
        control_input_folder="$2" 
        echo "++Input folder: ${control_input_folder}"
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
echo "MDMA subjects collected: ${mdma_subject_ids[@]}"
echo "Control subjects collected: ${control_subject_ids[@]}"

if [ ${#mdma_subject_ids[@]} -eq 0 ]; then
    echo "No MDMA subjects provided"
    exit 1
fi

if [ ${#control_subject_ids[@]} -eq 0 ]; then
    echo "No control subjects provided"
    exit 1
fi

if [ ! -d logs ]; then
    mkdir logs
fi

data_table="Subj group stimulus InputFile"$'\n'

for subject in ${mdma_subject_ids[@]}; do
      mask_epi_anat_files="${mask_epi_anat_files} ${mdma_input_folder}/${subject}.ses-1.results/mask_epi_anat.*+tlrc.HEAD"
      for stimulus in ${stimuli[@]}; do
          data_table+="${subject}    mdma  ${stimulus} ${mdma_input_folder}/${subject}.ses-1.results/stats.${subject}+tlrc[${stimulus}_blck#0_Coef]"$'\n'
      done
done

for subject in ${control_subject_ids[@]}; do
      mask_epi_anat_files="${mask_epi_anat_files} ${control_input_folder}/${subject}.ses-1.results/mask_epi_anat.*+tlrc.HEAD"
      for stimulus in ${stimuli[@]}; do
          data_table+="${subject}    control  ${stimulus} ${control_input_folder}/${subject}.ses-1.results/stats.${subject}+tlrc[${stimulus}_blck#0_Coef]"$'\n'
      done
done

if [ -f "group_mask_olap.7+tlrc.HEAD" ]; then
    rm group_mask_olap.7+tlrc.HEAD
fi

if [ -f "group_mask_olap.7+tlrc.BRIK.gz" ]; then
    rm group_mask_olap.7+tlrc.BRIK.gz
fi

echo $data_table

3dmask_tool -input ${mask_epi_anat_files} \
    -prefix group_mask_olap.7 \
    -frac 0.7

if [ -f "LME_MDMA_Control_log.txt" ]; then
    rm LME_MDMA_Control_log.txt
fi
if [ -f "LME_MDMA_Control+tlrc.BRIK.gz" ]; then
    rm LME_MDMA_Control+tlrc.BRIK.gz
fi
if [ -f "LME_MDMA_Control+tlrc.HEAD" ]; then
    rm LME_MDMA_Control+tlrc.HEAD;
fi

3dLMEr -prefix LME_MDMA_Control \
    -mask group_mask_olap.7+tlrc \
    -SS_type 3 \
    -model "group*stimulus+(1|Subj)" \
    -gltCode neg.mdma 'group : 1*mdma stimulus : 1*neg' \
    -gltCode pos.mdma 'group : 1*mdma stimulus : 1*pos' \
    -gltCode neut.mdma 'group : 1*mdma stimulus : 1*neut' \
    -gltCode neg.control 'group : 1*control stimulus : 1*neg' \
    -gltCode pos.control 'group : 1*control stimulus : 1*pos' \
    -gltCode neut.control 'group : 1*control stimulus : 1*neut' \
    -gltCode neg.mdma.ctrl.diff    'group : 1*mdma -1*control stimulus : 1*neg' \
    -gltCode pos.mdma.ctrl.diff    'group : 1*mdma -1*control stimulus : 1*pos' \
    -gltCode neut.mdma.ctrl.diff    'group : 1*mdma -1*control stimulus : 1*neut' \
    -gltCode neg.pos.diff 'group : 1*mdma -1*control stimulus : 1*neg -1*pos' \
    -gltCode neg.neut.diff 'group : 1*mdma -1*control stimulus : 1*neg -1*neut' \
    -gltCode pos.neut.diff 'group : 1*mdma -1*control stimulus : 1*pos -1*neut' \
    -dataTable ${data_table}

if [ ! -d chauffeur_3dlmer]; then
        mkdir chauffeur_3dlmer
fi

chi_interactions=("group" "stimulus" "group:stimulus")
for chi in "${chi_interactions[@]}"; do
    echo $chi
    @chauffeur_afni                                                         \
        -ulay               MNI152_2009_template.nii.gz                     \
        -ulay_range         0% 130%                                         \
        -olay               ./LME_MDMA_Control+tlrc.HEAD                    \
        -box_focus_slices   AMASK_FOCUS_ULAY                                \
        -func_range         3                                               \
        -cbar               Reds_and_Blues_Inv                              \
        -thr_olay_p2stat    0.05                                            \
        -thr_olay_pside     bisided                                         \
        -olay_alpha         Yes                                             \
        -olay_boxed         Yes                                             \
        -set_subbricks      -1 "$chi Chi-sq" "$chi Chi-sq"                            \
        -opacity            5                                               \
        -zerocolor          white                                           \
        -prefix             chauffeur_3dlmer/"$chi"                         \
        -set_xhairs         OFF                                             \
        -set_dicom_xyz      -10 0 0                                         \
        -delta_slices       6 15 10                                         \
        -label_color        black                                           \
        -montx 3 -monty 3                                                   \
        -label_mode 1 -label_size 4                                         \
        -do_clean
done

stimuli=("neg" "neut" "pos")
for stimulus in ${stimuli[@]}; do
    @chauffeur_afni                                                         \
        -ulay               MNI152_2009_template.nii.gz                     \
        -ulay_range         0% 130%                                         \
        -olay               ./LME_MDMA_Control+tlrc.HEAD                    \
        -box_focus_slices   AMASK_FOCUS_ULAY                                \
        -func_range         3                                               \
        -cbar               Reds_and_Blues_Inv                              \
        -thr_olay_p2stat    0.05                                            \
        -thr_olay_pside     bisided                                         \
        -olay_alpha         Yes                                             \
        -olay_boxed         Yes                                             \
        -set_subbricks      -1 "${stimulus}.mdma.ctrl.diff" "${stimulus}.mdma.ctrl.diff Z"                            \
        -opacity            5                                               \
        -zerocolor          white                                           \
        -prefix             chauffeur_3dlmer/${stimulus}.mdma.ctrl.diff                        \
        -set_xhairs         OFF                                             \
        -set_dicom_xyz      -10 0 0                                         \
        -delta_slices       6 15 10                                         \
        -label_color        black                                           \
        -montx 3 -monty 3                                                   \
        -label_mode 1 -label_size 4                                         \
        -do_clean
done