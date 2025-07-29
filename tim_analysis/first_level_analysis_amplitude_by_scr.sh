#!/bin/bash

echo "Starting first level analysis script"
echo "Please note, this script should only be run with bash"
echo "====================================================="
echo ""

OPTIND=1

# Define the short and long options
short_options="hs:r:wn:i:o:l:"
long_options="help,session:,runs:,warper,num_proc:,subjects:,input:,output:,conv:,lag:"
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
output_folder=""
events_conversion_script_path="./fMRIScripts/tim_analysis/convert_event_onset_files_war.sh"

subject_ids=()

#Indicate the session that needs to be analysed
session=1
session_prefix="ses-1"
num_procs=1
compute_sswarper=false
num_jobs=0
trs_removal=0
tr_length=2
runs=5

# Loop through the options
while true; do
    case ${1} in
    -h | --help)
        echo "Usage: $0 [-i input_folder] [-o output_folder] [-r runs] [-s session] [-w] [-n <nprocs>] [--conv event_onset_conversion_script_path] --subjects <sub1,sub2,...> sub-??*"
        echo
        echo "Options:"
        echo "  -h, --help      Show this help message and exit."
        echo "  -i, --input     Specify the location of the input."
        echo "  -o, --output    Specify the location of the output."
        echo "  -s, --session   Specify the session number."
        echo "  -r, --runs      Specify the amount of TIM runs. Default is 5."
        echo "  -w, --warper    Use SSWarper."
        echo "  -n, --num_procs  Specify the number of processors to use."
        echo "  -l, --lag       Specify lag time in sec, to be reduced from the events timing."
        echo "  --conv          Specify path for the events_onset conversion script"
        echo "  --subjects       Specify a comma-separated list of subject IDs."
        echo
        echo "Example:"
        echo "  $0 -w -s 2 -r 6 --subjects sub-01,sub-03,sub-05 --input /path/to/input --output /path/to/output"
        exit 1
        ;;
    -s | --session)
        session=$2
        session_prefix="ses-$session"
        echo "++Session mentioned is $session"
        shift 2
        ;;
    -r | --runs)
        runs=$2
        echo "++runs mentioned are $runs"
        shift 2
        ;;
    -w | --warper)
        compute_sswarper=true
        shift
        ;;
    -n | --num_procs)
        num_procs=$2
        shift 2
        ;;
    -l | --lag)
        lag=$2
        shift 2
        ;;
    --subjects)
        IFS=',' read -ra subject_ids <<<"$2" # Append the subject ID to the array
        echo "++Subject IDs: ${subject_ids[@]}"
        shift 2
        ;;
    -i | --input)
        input_folder=$2
        echo "++Input folder: ${input_folder}"
        shift 2
        ;;
    -o | --output)
        output_folder=$2
        echo "++Output folder: ${output_folder}"
        shift 2
        ;;
    --conv)
        events_conversion_script_path=$2
        echo "++Onset conversion script path: ${events_conversion_script_path}"
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

if [ ! -d logs ]; then
    mkdir logs
fi

lag+=($trs_removal*$tr_length)

task() {
    echo "Started running for ${subj} with PID $PID"

    echo "Moving previous outputs for subject"
    time=$(date +"%H").$(date +%M)
    old_results_path=${1}.$session_prefix.results
    if [ -d "${output_folder}/$old_results_path" ]; then
        if [ -f proc.${1} ]; then
            mv ${output_folder}/proc.${1} ${output_folder}/${old_results_path}
        fi
        if [ -f "${output_folder}/output.proc.${1}" ]; then
            mv ${output_folder}/output.proc.${1} ${output_folder}/${old_results_path}
        fi
        if [ ! -d ${output_folder}/old_results ]; then
            mkdir ${output_folder}/old_results
        fi
        mv ${output_folder}/${old_results_path} ${output_folder}/old_results/${old_results_path}.old.${time}
    fi
    if [ -f proc.${1} ]; then
        rm proc.${1}
    fi
    if [ -f output.proc.${1} ]; then
        rm output.proc.${1}
    fi

    echo "Cleaning up old data on Dropbox"
    if [ -d ~/Dropbox/${1}.scr.old ]; then
        rm -r ~/Dropbox/${1}.scr.old
    fi

    echo "Backing up previous results on Dropbox"
    if [ -d ~/Dropbox/${1}.scr ]; then
        mv ~/Dropbox/${1}.scr ~/Dropbox/${1}.scr.old
    fi

    mkdir ~/Dropbox/${1}.scr

    echo "Preparing timing files for subject ${1}"
    bash ${events_conversion_script_path} -s ${session} -r ${runs} --subject ${1} --input ${input_folder} --lag ${lag}

    if [ $compute_sswarper = true ]; then
        echo "Running SSWarper on ${1}"
        sswarper2 -input ${input_folder}/${1}/${session_prefix}/anat/${1}_${session_prefix}_T1w.nii.gz \
            -base MNI152_2009_template_SSW.nii.gz \
            -subid ${1} -odir ${input_folder}/${1}/$session_prefix/anat_warped \
            -giant_move \
            -cost_nl_final nmi \
            -minp 8 \
            -deoblique_refitly
    fi

    dsets=""
    for i in $(seq 1 $runs); do
        dsets+="-dsets_me_run \
            ${input_folder}/${1}/${session_prefix}/func/${1}_${session_prefix}_task-tim_run-${i}_echo-1_bold.nii.gz \
            ${input_folder}/${1}/${session_prefix}/func/${1}_${session_prefix}_task-tim_run-${i}_echo-2_bold.nii.gz \
            ${input_folder}/${1}/${session_prefix}/func/${1}_${session_prefix}_task-tim_run-${i}_echo-3_bold.nii.gz "
    done

    echo "Running afni_proc.py for subject ${1}"
    afni_proc.py \
        -subj_id ${1} \
        ${dsets} \
        -echo_times 13.6 25.96 38.3 \
        -copy_anat \
            ${input_folder}/${1}/${session_prefix}/anat_warped/anatSS.${1}.nii \
        -anat_has_skull no \
        -anat_follower anat_w_skull anat ${input_folder}/${1}/${session_prefix}/anat_warped/anatU.${1}.nii \
        -blocks \
            tshift align tlrc volreg mask combine blur scale regress \
        -html_review_style pythonic \
        -align_unifize_epi local \
        -align_opts_aea \
        -cost lpc+ZZ \
        -giant_move \
        -check_flip \
        -volreg_align_to MIN_OUTLIER \
        -volreg_align_e2a \
        -volreg_tlrc_warp \
        -volreg_compute_tsnr yes \
        -mask_epi_anat yes \
        -mask_segment_anat yes \
        -combine_method OC \
        -blur_size 4 \
        -tlrc_base MNI152_2009_template.nii.gz \
        -tlrc_NL_warp \
        -tlrc_NL_warped_dsets \
            ${input_folder}/${1}/${session_prefix}/anat_warped/anatQQ.${1}.nii \
            ${input_folder}/${1}/${session_prefix}/anat_warped/anatQQ.${1}.aff12.1D \
            ${input_folder}/${1}/${session_prefix}/anat_warped/anatQQ.${1}_WARP.nii \
        -regress_stim_times \
            ${input_folder}/${1}/${session_prefix}/func/timings/scr_amp.1D \
        -regress_stim_labels SCR \
        -regress_stim_types AM2 \
        -regress_basis 'BLOCK(2,1)' \
        -regress_opts_3dD \
        -jobs 8 \
        -regress_motion_per_run \
        -regress_censor_motion 0.5 \
        -regress_censor_outliers 0.05 \
        -regress_reml_exec \
        -regress_compute_fitts \
        -regress_make_ideal_sum sum_ideal.1D \
        -regress_est_blur_epits \
        -regress_est_blur_errts \
        -regress_run_clustsim no \
        -radial_correlate_blocks tcat volreg regress \
        -remove_preproc_files \
        -execute

    echo "Backing up QC to Dropbox"
    cp -R ${1}.QC_${1} ~/Dropbox/${1}.scr/QC

    echo "Done running afni_proc.py for subject ${1}"
    echo "Exporting images using @chauffeur_afni"
    regressors=("SCR#0" "SCR#1")
    for reg in ${regressors[@]}; do
        @chauffeur_afni                                             \
            -ulay               ${1}.results/anat_final.*.HEAD      \
            -ulay_range         0% 130%                             \
            -olay               ${1}.results/stats.${1}+tlrc.HEAD   \
            -box_focus_slices   AMASK_FOCUS_ULAY                    \
            -func_range         3                                   \
            -cbar               Reds_and_Blues_Inv                  \
            -thr_olay_p2stat    0.05                                \
            -thr_olay_pside     bisided                             \
            -olay_alpha         Yes                                 \
            -olay_boxed         Yes                                 \
            -set_subbricks      -1 "${reg}_Coef" "${reg}_Tstat" \
            -clusterize        "-NN 2 -clust_nvox 40"               \
            -opacity            5                                   \
            -prefix             ${1}.results/chauffeur/${reg}          \
            -set_xhairs         OFF                                 \
            -montx 3 -monty 3                                       \
            -label_mode 1 -label_size 4
    done

    echo "Backing up chauffeur to Dropbox"
    cp -R ${1}/chauffeur ~/Dropbox/${1}.scr/chauffeur

    echo "Moving results to sub-folder by session"
    mv ${1}.results ${output_folder}/${1}.${session_prefix}.results
    echo "Done"
}

if [ $num_procs -eq 1 ]; then
    for subj in ${subject_ids[@]}; do
        task "$subj" > logs/${subj}.txt
    done
else
    for subj in ${subject_ids[@]}; do
        while [ $num_jobs -ge $num_procs ]
        do
            wait -n
        done
        num_jobs=$num_jobs+1
        task "$subj" > logs/${subj}.txt && num_jobs=$num_jobs-1 &
    done
fi

wait
echo "All processes finished successfully!"