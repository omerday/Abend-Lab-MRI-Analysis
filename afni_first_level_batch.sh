#!/bin/bash

OPTIND=1

# Define the short and long options
short_options="hs:wn:i:o:"
long_options="help,session:,warper,num_proc:,subjects:,input:,output:"
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
output_folder=""

subject_ids=()

#Indicate the session that needs to be analysed
session=1
session_prefix=""
num_procs=1
compute_sswarper=false
num_jobs=0

# Loop through the options
while true; do
  case ${1} in
    -h|--help)
      echo "Usage: $0 [-i input_folder] [-o output_folder] [-s session] [-w] [-n <nprocs>] --subjects <sub1,sub2,...> sub-??*"
      echo
      echo "Options:"
      echo "  -h, --help      Show this help message and exit."
      echo "  -i, --input     Specify the location of the input."
      echo "  -o, --output    Specify the location of the output."
      echo "  -s, --session   Specify the session number."
      echo "  -w, --warper    Use SSWarper."
      echo "  -n, --num_proc  Specify the number of processors to use."
      echo "  --subjects       Specify a comma-separated list of subject IDs."
      echo
      echo "Example:"
      echo "  $0 -s 2 --subject sub-001,sub-003,sub-005 -w /path/to/warper_output"
      exit 1
      ;;
    -s|--session)
      session=$2
      session_prefix="ses-$session"
      echo "++Session mentioned is $session"
      shift 2
      ;;
    -w|--warper)
      compute_sswarper=true
      shift
      ;;
    -n|--num_proc)
        num_proc=$2
        shift 2
        ;;
    --subjects)
        IFS=',' read -ra subject_ids <<< "$2" # Append the subject ID to the array
        echo "++Subject IDs: ${subject_ids[@]}"
        shift 2
        ;;
    -i|--input)
        input_folder=$2
        shift 2
        ;;
    -o|--output)
        output_folder=$2
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

if [ ${#subject_ids[@]} -eq 0 ]; then
    echo "No subjects provided"
    exit 1
fi

task() {
    echo "Started running for ${subj} with PID $PID"

    echo "Moving previous outputs for subject"
    time=`date +"%H"`.`date +%M`
    old_results_path=${1}.$session_prefix.results
    if [ -f "${output_folder}/$old_results_path" ]; then
        if [ -f proc.${1} ]; then
            mv ${output_folder}/proc.${1} ${output_folder}/${old_results_path}
        fi
        if [ -f "${output_folder}/output.proc.${1}" ]; then
            mv ${output_folder}/output.proc.${1} ${output_folder}/${old_results_path}
        fi
        mv ${output_folder}/${old_results_path} ${output_folder}/old_results/${old_results_path}.old.${time}
    else
        if [ -f proc.${1} ]; then
            rm proc.${1}
        fi
        if [ -f output.proc.${1} ]; then
            rm output.proc.${1}
        fi
    fi

    echo "Preparing timing files for subject ${1}"
    echo ${1} > subjList.txt
    sh convert_event_onset_files.sh -s ${session}

    if [ $compute_sswarper = true ]; then
    echo "Running SSWarper on ${1}"
    @SSwarper -input ${input_folder}/${1}/$session_prefix/anat/${1}_${session_prefix}_T1w.nii.gz \
            -base MNI152_2009_template_SSW.nii.gz \
            -subid ${1} -odir ${input_folder}/${1}/$session_prefix/anat_warped \
            -giant_move \
            -cost_nl_final lpa \
            -minp 8
    fi

    echo "Running afni_proc.py for subject ${1}"
    afni_proc.py \
        -subj_id ${1} \
        -dsets_me_run \
            ${input_folder}/${1}/$session_prefix/func/${1}_$session_prefix_task-war_run-1_echo-1_bold.nii.gz \
            ${input_folder}/${1}/$session_prefix/func/${1}_$session_prefix_task-war_run-1_echo-2_bold.nii.gz \
            ${input_folder}/${1}/$session_prefix/func/${1}_$session_prefix_task-war_run-1_echo-3_bold.nii.gz \
        -echo_times 13.6 25.96 38.3 \
        -dsets_me_run \
            ${input_folder}/${1}/$session_prefix/func/${1}_$session_prefix_task-war_run-2_echo-1_bold.nii.gz \
            ${input_folder}/${1}/$session_prefix/func/${1}_$session_prefix_task-war_run-2_echo-2_bold.nii.gz \
            ${input_folder}/${1}/$session_prefix/func/${1}_$session_prefix_task-war_run-2_echo-3_bold.nii.gz \
        -echo_times 13.6 25.96 38.3 \
        -copy_anat \
            ${input_folder}/${1}/$session_prefix/anat/${1}_$session_prefix_T1w.nii.gz \
        -blocks \
            tshift align tlrc volreg mask blur scale combine regress \
        -mask_epi_anat yes \
        -mask_apply anat \
        -tcat_remove_first_trs 5 \
        -html_review_style pythonic \
        -align_unifize_epi local \
        -align_opts_aea \
            -cost lpc+ZZ \
            -giant_move \
            -check_flip \
        -volreg_align_to MIN_OUTLIER \
        -volreg_align_e2a \
        -volreg_tlrc_warp \
        -mask_epi_anat yes \
        -mask_segment_anat yes \
        -volreg_compute_tsnr yes \
        -tlrc_base MNI152_2009_template.nii.gz \
        -tlrc_NL_warp \
        -tlrc_NL_warped_dsets \
            ${input_folder}/${1}/$session_prefix/anat_warped/anatQQ.${1}.nii \
            ${input_folder}/${1}/$session_prefix/anat_warped/anatQQ.${1}.aff12.1D \
            ${input_folder}/${1}/$session_prefix/anat_warped/anatQQ.${1}_WARP.nii \
        -regress_stim_times       \
            ${input_folder}/${1}/$session_prefix/func/negative_block.1D \
            ${input_folder}/${1}/$session_prefix/func/positive_block.1D \
            ${input_folder}/${1}/$session_prefix/func/neutral_block.1D \
            ${input_folder}/${1}/$session_prefix/func/rest.1D \
        -regress_stim_labels      neg_blck pos_blck neut_blck rest   \
        #TODO: Try and use regress_stim_times
        -regress_basis            'BLOCK(22,1)' \
        -regress_opts_3dD \
            -jobs 8 \
            -gltsym 'SYM: neg_blck -neut_blck' \
            -glt_label 1 neg-neut-blck \
            -gltsym 'SYM: neg_blck -rest' \
            -glt_label 2 neg_blck-rest \
            -gltsym 'SYM: pos_blck -neut_blck' \
            -glt_label 3 pos-neut-blck \
            -gltsym 'SYM: neg_blck -pos_blck' \
            -glt_label 4 neg-pos-blck \
        -regress_motion_per_run                                          \
        -regress_censor_motion    0.5                                    \
        -regress_censor_outliers  0.05                                   \
        -regress_reml_exec                                               \
        -regress_compute_fitts                                           \
        -regress_make_ideal_sum   sum_ideal.1D                           \
        -regress_est_blur_epits                                          \
        -regress_est_blur_errts                                          \
        -regress_run_clustsim     no                                     \
        -execute           
        #TODO: Multiply GM with the activity, and run clustsim on the result (Maybe post-script?)                                               
    echo "Done running afni_proc.py for subject ${1}"
    echo "Moving results to sub-folder by session"
    mv ${1}.results ${output_folder}/${1}.$session_prefix.results
    echo "Done"
}

if [ $num_procs -eq 1 ]; then
    for subj in $subject_ids; do
        task "$subj" > ${subj}.txt
    done
else
    for subj in $subject_ids; do
        while [ $num_jobs -ge $num_procs ]; do
            wait -n
        done
        num_jobs=$num_jobs+1
        task "$subj" > ${subj}.txt && num_jobs=$num_jobs-1 &
    done
fi

wait
echo "All processes finished successfully!"