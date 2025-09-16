
import argparse
import os
import subprocess
import toml
from functools import partial

def main():
    """Main function to run the group analysis pipeline."""
    parser = argparse.ArgumentParser(description="fMRI Group Analysis Pipeline Runner")
    parser.add_argument("--analysis", required=True, help="Specify the first-level analysis model (e.g., pain_by_rating).")
    parser.add_argument("--contrast", required=True, help="Specify the contrast/sub-brick to analyze (e.g., 'PAIN#0_Coef').")
    parser.add_argument("--label", required=True, help="A descriptive label for this group analysis run (e.g., all_subjects_controls).")
    parser.add_argument("--session", default="1", help="Specify the session number (e.g., 1).")
    parser.add_argument("--subjects", help="Comma-separated list of subject IDs to include. Overrides config.")

    args = parser.parse_args()

    try:
        main_config = toml.load("analysis_configs/main_config.toml")
        analysis_models = toml.load("analysis_configs/analysis_models.toml")
    except FileNotFoundError as e:
        print(f"Error: Configuration file not found. {e}")
        return

    subjects_to_process = []
    if args.subjects:
        subjects_to_process = args.subjects.split(',')
    else:
        model = analysis_models.get(args.analysis, {})
        subjects_to_process = model.get("subjects", main_config.get("all_subjects", []))

    if not subjects_to_process:
        print("No subjects found to process. Check your configuration and command-line arguments.")
        return

    print(f"--- Starting Group Analysis: '{args.label}' ---")
    print(f"Analysis Model: {args.analysis}")
    print(f"Contrast: {args.contrast}")
    print(f"Including subjects: {', '.join(subjects_to_process)}")

    # Construct the input file list
    base_output_dir = main_config["output_dir"]
    session_prefix = f"ses-{args.session}"
    
    input_files = []
    for subj in subjects_to_process:
        # Path to the stats file from the first-level analysis
        stats_file = f"{base_output_dir}/{subj}/{session_prefix}/{args.analysis}/stats.{subj}_{args.analysis}+tlrc.HEAD[{args.contrast}]"
        if not os.path.exists(stats_file.split('[')[0]):
            print(f"Warning: Stats file not found for subject {subj}. Skipping. Path: {stats_file}")
            continue
        input_files.append(f"{subj} {stats_file}")

    if not input_files:
        print("Error: No valid input files found for any subject. Aborting group analysis.")
        return

    # Define output directory for the group analysis
    group_output_dir = f"{base_output_dir}/group/{args.analysis}/{args.label}"
    os.makedirs(group_output_dir, exist_ok=True)

    # Run the group analysis script
    script_path = "scripts/run_group_analysis.sh"
    command = [
        "bash", script_path,
        "--output_dir", group_output_dir,
        "--label", args.label,
        "--contrast_name", args.contrast.split('#')[0], # e.g., 'PAIN'
        "--setA_label", args.contrast, # e.g., 'PAIN#0_Coef'
    ] + input_files

    print(f"Executing: {' '.join(command)}")
    log_file_path = f"logs/group_analysis_{args.label}.log"

    with open(log_file_path, "w") as log_file:
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, cwd=group_output_dir)
        process.wait()

    if process.returncode == 0:
        print(f"Successfully completed group analysis. Results are in: {group_output_dir}")
    else:
        print(f"Error running group analysis. Check log for details: {log_file_path}")

if __name__ == "__main__":
    main()
