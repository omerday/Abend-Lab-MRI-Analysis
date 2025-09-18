import argparse
import os
import subprocess
import toml
from concurrent.futures import ProcessPoolExecutor
from functools import partial

def run_step(subject, session, config, analysis_name, step_name):
    """Helper function to run a single shell script for a subject."""
    script_map = {
        "create_timings": "00_create_timings.sh",
        "preprocess_anat": "01_preprocess_anat.sh",
        "preprocess_func": "02_preprocess_func.sh",
        "glm": "03_run_glm.sh",
    }
    script_name = script_map.get(step_name)
    if not script_name:
        print(f"Error: Invalid step name '{step_name}'")
        return False

    script_path = os.path.join("scripts", script_name)
    if not os.path.exists(script_path):
        print(f"Error: Script not found at {script_path}")
        return False

    command = [
        "bash", script_path,
        "--subject", subject,
        "--session", session,
        "--input", config["input_dir"],
    ]
    
    if step_name != "create_timings":
        command.extend(["--output", config["output_dir"]])
        
    if analysis_name and step_name == "glm":
        command.extend(["--analysis", analysis_name])

    print(f"Executing for {subject}: {' '.join(command)}")
    
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"{subject}_{step_name}.log")

    with open(log_file_path, "w") as log_file:
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT)
        process.wait()

    if process.returncode == 0:
        print(f"Successfully completed {step_name} for {subject}. Log: {log_file_path}")
        return True
    else:
        print(f"Error running {step_name} for {subject}. Check log for details: {log_file_path}")
        return False

def run_group_analysis(config, analysis_models, args):
    """Runs the group analysis for a given model."""
    if not args.analysis:
        print("Error: --analysis is required for the group_analysis step.")
        return

    model = analysis_models.get(args.analysis, {})
    if not model:
        print(f"Error: Analysis model '{args.analysis}' not found.")
        return

    group_analysis_config = model.get("group_analysis")
    if not group_analysis_config:
        print(f"Error: No group_analysis configuration for model '{args.analysis}'.")
        return

    subjects = model.get("subjects", config.get("all_subjects", []))
    if not subjects:
        print("No subjects found for this analysis.")
        return

    script_path = os.path.join("scripts", "04_run_group_analysis.sh")
    if not os.path.exists(script_path):
        print(f"Error: Group analysis script not found at {script_path}")
        return

    command = [
        "bash", script_path,
        "--analysis", args.analysis,
        "--input", config["output_dir"],
        "--output", config["output_dir"],
        "--subjects", ",".join(subjects),
        "--session", args.session,
        "--regressor", group_analysis_config["regressor"],
        "--label", group_analysis_config["label"],
    ]

    print(f"Executing group analysis: {' '.join(command)}")
    
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, f"group_analysis_{args.analysis}.log")

    with open(log_file_path, "w") as log_file:
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT)
        process.wait()

    if process.returncode == 0:
        print(f"Successfully completed group analysis for {args.analysis}. Log: {log_file_path}")
    else:
        print(f"Error running group analysis for {args.analysis}. Check log for details: {log_file_path}")

def process_subject(subject, args):
    """Runs the requested pipeline steps for a single subject."""
    # Load configs inside the worker process to avoid pickling issues.
    try:
        main_config = toml.load("analysis_configs/main_config.toml")
        analysis_models = toml.load("analysis_configs/analysis_models.toml")
    except FileNotFoundError as e:
        print(f"Error in worker for {subject}: Configuration file not found. {e}")
        return

    print(f"--- Starting Pipeline for Subject: {subject}, Session: {args.session} ---")
    
    steps_to_run = []
    if args.step == 'all':
        steps_to_run = ["create_timings", "preprocess_anat", "preprocess_func", "glm"]
    elif args.step == 'preprocess':
        steps_to_run = ["create_timings", "preprocess_anat", "preprocess_func"]
    else:
        steps_to_run = [args.step]

    # This logic needs to be inside the worker now that configs are loaded here.
    analysis_name = args.analysis
    if args.analysis and args.step in ["glm", "all"]:
        model = analysis_models.get(args.analysis, {})
        if not model:
            print(f"Warning for {subject}: Analysis model '{args.analysis}' not found in analysis_models.toml.")

    for step in steps_to_run:
        success = run_step(
            subject=subject,
            session=args.session,
            config=main_config,
            analysis_name=args.analysis,
            step_name=step
        )
        if not success:
            print(f"Stopping pipeline for {subject} because step '{step}' failed.")
            break

def main():
    """Main function to run the analysis pipeline."""
    parser = argparse.ArgumentParser(description="fMRI Analysis Pipeline Runner")
    parser.add_argument("--subject", help="Specify a single subject ID to process (e.g., sub-001).")
    parser.add_argument("--analysis", help="Specify the analysis model to run for the 'glm' or 'group_analysis' step.")
    parser.add_argument("--step", choices=["preprocess", "create_timings", "preprocess_anat", "preprocess_func", "glm", "all", "group_analysis"], required=True, help="The processing step to execute.")
    parser.add_argument("--session", default="1", help="Specify the session number (e.g., 1).")
    parser.add_argument("--n_procs", type=int, default=1, help="Number of subjects to process in parallel.")

    args = parser.parse_args()

    try:
        main_config = toml.load("analysis_configs/main_config.toml")
        analysis_models = toml.load("analysis_configs/analysis_models.toml")
    except FileNotFoundError as e:
        print(f"Error: Configuration file not found. {e}")
        return

    if args.step == "group_analysis":
        run_group_analysis(main_config, analysis_models, args)
        return

    subjects_to_process = []
    # Determine subjects to process in the main thread
    if args.subject:
        subjects_to_process = [args.subject]
    elif args.analysis:
        model = analysis_models.get(args.analysis, {})
        subjects_to_process = model.get("subjects", main_config.get("all_subjects", []))
    else:
        subjects_to_process = main_config.get("all_subjects", [])

    # Validate analysis model existence before starting parallel jobs
    if args.analysis and args.analysis not in analysis_models:
        print(f"Error: Analysis model '{args.analysis}' not found in analysis_configs/analysis_models.toml. Aborting.")
        return

    if not subjects_to_process:
        print("No subjects found to process. Check your configuration and command-line arguments.")
        return

    print(f"Processing subjects: {', '.join(subjects_to_process)}")
    print(f"Number of parallel processes: {args.n_procs}")

    # Create a partial function with fixed arguments for the worker processes
    worker_function = partial(process_subject, args=args)

    if args.n_procs > 1:
        with ProcessPoolExecutor(max_workers=args.n_procs) as executor:
            # Use map to run the worker function for each subject
            list(executor.map(worker_function, subjects_to_process))
    else:
        # Run sequentially if n_procs is 1
        for subject in subjects_to_process:
            worker_function(subject)

    # After processing all subjects, run group analysis if step is 'all' and analysis is specified
    if args.step == "all" and args.analysis:
        print("\n--- All first-level analyses complete, starting group analysis ---")
        run_group_analysis(main_config, analysis_models, args)

    print("--- All processing complete ---")

if __name__ == "__main__":
    main()
