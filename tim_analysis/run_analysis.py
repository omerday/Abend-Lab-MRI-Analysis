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

def process_subject(subject, args, main_config, analysis_models):
    """Runs the requested pipeline steps for a single subject."""
    print(f"--- Starting Pipeline for Subject: {subject}, Session: {args.session} ---")
    
    steps_to_run = []
    if args.step == 'all':
        steps_to_run = ["create_timings", "preprocess_anat", "preprocess_func", "glm"]
    elif args.step == 'preprocess':
        steps_to_run = ["create_timings", "preprocess_anat", "preprocess_func"]
    else:
        steps_to_run = [args.step]

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
    parser.add_argument("--analysis", help="Specify the analysis model to run for the 'glm' step.")
    parser.add_argument("--step", choices=["preprocess", "create_timings", "preprocess_anat", "preprocess_func", "glm", "all"], required=True, help="The processing step to execute.")
    parser.add_argument("--session", default="1", help="Specify the session number (e.g., 1).")
    parser.add_argument("--n_procs", type=int, default=1, help="Number of subjects to process in parallel.")

    args = parser.parse_args()

    try:
        main_config = toml.load("analysis_configs/main_config.toml")
        analysis_models = toml.load("analysis_configs/analysis_models.toml")
    except FileNotFoundError as e:
        print(f"Error: Configuration file not found. {e}")
        return

    subjects_to_process = []
    if args.subject:
        subjects_to_process = [args.subject]
    elif args.analysis:
        subjects_to_process = model.get("subjects", main_config.get("all_subjects", []))
    else:
        subjects_to_process = main_config.get("all_subjects", [])

    if args.analysis and args.step in ["glm", "all"]:
        model = analysis_models.get(args.analysis, {})

    if not subjects_to_process:
        print("No subjects found to process. Check your configuration and command-line arguments.")
        return

    print(f"Processing subjects: {', '.join(subjects_to_process)}")
    print(f"Number of parallel processes: {args.n_procs}")

    # Create a partial function with fixed arguments for the worker processes
    worker_function = partial(process_subject, args=args, main_config=main_config, analysis_models=analysis_models)

    if args.n_procs > 1:
        with ProcessPoolExecutor(max_workers=args.n_procs) as executor:
            # Use map to run the worker function for each subject
            list(executor.map(worker_function, subjects_to_process))
    else:
        # Run sequentially if n_procs is 1
        for subject in subjects_to_process:
            worker_function(subject)

    print("--- All processing complete ---")

if __name__ == "__main__":
    main()