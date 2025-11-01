import argparse
import os
import subprocess
import toml
from concurrent.futures import ProcessPoolExecutor
from functools import partial

def run_step(subject, session, config, analysis_name, step_name, extra_args=None):
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

    if extra_args:
        command.extend(extra_args)

    print(f"Executing for {subject}: {' '.join(command)}")

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    log_name_parts = [subject, step_name]
    if analysis_name and step_name == "glm":
        log_name_parts.append(analysis_name)
    log_file_path = os.path.join(log_dir, f"{'_'.join(log_name_parts)}.log")

    with open(log_file_path, "w") as log_file:
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT)
        process.wait()

    if process.returncode == 0:
        print(f"Successfully completed {step_name} for {subject}. Log: {log_file_path}")
        return True
    else:
        print(f"Error running {step_name} for {subject}. Check log for details: {log_file_path}")
        return False

def process_subject(subject_id, args, main_config, analysis_models):
    """Runs the requested pipeline steps for a single subject."""
    print(f"--- Starting Pipeline for Subject: {subject_id}, Session: {args.session} ---")

    steps_to_run = []
    if args.step == 'all':
        steps_to_run = ["create_timings", "preprocess_anat", "preprocess_func", "glm"]
    elif args.step == 'preprocess':
        steps_to_run = ["create_timings", "preprocess_anat", "preprocess_func"]
    else:
        steps_to_run = [args.step]

    analysis_names = args.analysis
    if analysis_names and args.step in ["glm", "all"]:
        for analysis_name in analysis_names:
            if analysis_name not in analysis_models:
                print(f"Warning for {subject_id}: Analysis model '{analysis_name}' not found in analysis_models.toml.")

    # Find subject-specific config
    subject_config = next((s for s in main_config.get("subjects", []) if s.get("id") == subject_id), {})
    # Find session-specific config within the subject's config
    session_id_to_find = int(args.session)
    session_config = next((ses for ses in subject_config.get("sessions", []) if ses.get("id") == session_id_to_find), {})

    lag_block_1 = session_config.get("lag_block_1", 0)
    lag_block_2 = session_config.get("lag_block_2", 0)

    for step in steps_to_run:
        extra_args = None
        if step == 'create_timings':
            extra_args = ["--lag_block_1", str(lag_block_1), "--lag_block_2", str(lag_block_2)]

        if step == 'glm':
            if not analysis_names:
                print(f"Error for {subject_id}: --analysis is required for 'glm' step.")
                break

            all_glm_success = True
            for analysis_name in analysis_names:
                print(f"--- Running GLM analysis '{analysis_name}' for Subject: {subject_id} ---")
                success = run_step(
                    subject=subject_id,
                    session=args.session,
                    config=main_config,
                    analysis_name=analysis_name,
                    step_name=step,
                    extra_args=extra_args
                )
                if not success:
                    all_glm_success = False
                    break
            if not all_glm_success:
                print(f"Stopping pipeline for {subject_id} because a GLM step failed.")
                break
        else:
            success = run_step(
                subject=subject_id,
                session=args.session,
                config=main_config,
                analysis_name=None,
                step_name=step,
                extra_args=extra_args
            )
            if not success:
                print(f"Stopping pipeline for {subject_id} because step '{step}' failed.")
                break

def main():
    """Main function to run the analysis pipeline."""
    parser = argparse.ArgumentParser(description="fMRI Analysis Pipeline Runner for WAR task")
    parser.add_argument("--subject", help="Specify a single subject ID to process (e.g., sub-AL01). Overrides subject lists in configs.")
    parser.add_argument("--analysis", nargs='+', help="Specify one or more analysis models to run for the 'glm' or 'all' step.")
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

    subjects_to_process_ids = []
    if args.subject:
        subjects_to_process_ids = [args.subject]
    elif args.analysis and args.step in ["glm", "all"]:
        first_analysis = args.analysis[0]
        model = analysis_models.get(first_analysis, {})
        # Use subjects defined in the model, or fall back to all subjects from main_config
        if "subjects" in model: 
            subjects_to_process_ids = model["subjects"]
        else: # Fallback to global subjects if not specified in analysis model
            subjects_to_process_ids = [s["id"] for s in main_config.get("subjects", [])]
    else:
        subjects_to_process_ids = [s["id"] for s in main_config.get("subjects", [])]

    if not subjects_to_process_ids:
        print("No subjects found to process. Check your configuration and command-line arguments.")
        return

    # Validate analysis model existence before starting parallel jobs
    if args.analysis:
        for analysis_name in args.analysis:
            if analysis_name not in analysis_models:
                print(f"Error: Analysis model '{analysis_name}' not found in analysis_configs/analysis_models.toml. Aborting.")
                return
    
    print(f"Processing subjects: { ', '.join(subjects_to_process_ids)}")
    print(f"Number of parallel processes: {args.n_procs}")

    worker_func = partial(process_subject, args=args, main_config=main_config, analysis_models=analysis_models)

    if args.n_procs > 1 and len(subjects_to_process_ids) > 1:
        with ProcessPoolExecutor(max_workers=args.n_procs) as executor:
            list(executor.map(worker_func, subjects_to_process_ids))
    else:
        for subject_id in subjects_to_process_ids:
            worker_func(subject_id)

    print("--- All processing complete ---")

if __name__ == "__main__":
    main()
