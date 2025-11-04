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
    # Find subject-specific config
    subject_config = next((s for s in main_config.get("subjects", []) if s.get("id") == subject_id), None)
    if not subject_config:
        print(f"Warning for {subject_id}: Subject configuration not found in main_config.toml. Skipping.")
        return

    sessions_to_process_configs = []
    if args.session:
        try:
            session_id_to_find = int(args.session)
            session_config = next((ses for ses in subject_config.get("sessions", []) if ses.get("id") == session_id_to_find), None)
            if not session_config:
                print(f"Error for {subject_id}: Session '{args.session}' not found in main_config.toml for this subject. Aborting.")
                return
            sessions_to_process_configs.append(session_config)
        except ValueError:
            print(f"Error: --session must be an integer. Got '{args.session}'.")
            return
    else:
        sessions_to_process_configs = subject_config.get("sessions", [])
        if not sessions_to_process_configs:
            print(f"Warning for {subject_id}: No sessions found in main_config.toml and no session specified. Skipping.")
            return

    for session_config in sessions_to_process_configs:
        session_id_str = str(session_config["id"])
        print(f"--- Starting Pipeline for Subject: {subject_id}, Session: {session_id_str} ---")

        steps_to_run = []
        if args.step == 'all':
            steps_to_run = ["create_timings", "preprocess_anat", "preprocess_func", "glm"]
        elif args.step == 'preprocess':
            steps_to_run = ["create_timings", "preprocess_anat", "preprocess_func"]
        else:
            steps_to_run = [args.step]

        analysis_names = args.analysis
        if not analysis_names and args.step in ["glm", "all"]:
            analysis_names = list(analysis_models.keys())

        if analysis_names and args.step in ["glm", "all"]:
            for analysis_name in analysis_names:
                if analysis_name not in analysis_models:
                    print(f"Warning for {subject_id}: Analysis model '{analysis_name}' not found in analysis_models.toml.")

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
                    analysis_model_config = analysis_models.get(analysis_name, {})
                    requires_scr = analysis_model_config.get("requires_scr", False)
                    session_has_scr = session_config.get("has_scr", False)

                    if requires_scr and not session_has_scr:
                        print(f"Skipping analysis '{analysis_name}' for subject {subject_id}, session {session_id_str} because it requires SCR data which is not available for this session.")
                        continue

                    print(f"--- Running GLM analysis '{analysis_name}' for Subject: {subject_id}, Session: {session_id_str} ---")
                    success = run_step(
                        subject=subject_id,
                        session=session_id_str,
                        config=main_config,
                        analysis_name=analysis_name,
                        step_name=step,
                        extra_args=extra_args
                    )
                    if not success:
                        all_glm_success = False
                        break
                if not all_glm_success:
                    print(f"Stopping pipeline for {subject_id}, Session {session_id_str} because a GLM step failed.")
                    break
            else:
                success = run_step(
                    subject=subject_id,
                    session=session_id_str,
                    config=main_config,
                    analysis_name=None,
                    step_name=step,
                    extra_args=extra_args
                )
                if not success:
                    print(f"Stopping pipeline for {subject_id}, Session {session_id_str} because step '{step}' failed.")
                    break

def run_group_analysis(args, config, analysis_models):
    """Runs a specified group-level analysis."""
    if not args.analysis or len(args.analysis) > 1:
        print("Error: Please specify exactly one first-level analysis model using --analysis.")
        return
    analysis_name = args.analysis[0]

    if not args.group_model:
        print("Error: Please specify a group analysis model using --group_model.")
        return

    # Find the first-level analysis model
    f_level_model = analysis_models.get(analysis_name)
    if not f_level_model:
        print(f"Error: First-level analysis '{analysis_name}' not found.")
        return

    # Find the group analysis model within the first-level model
    group_model_config = next((g for g in f_level_model.get("group_analyses", []) if g["name"] == args.group_model), None)
    if not group_model_config:
        print(f"Error: Group analysis model '{args.group_model}' not found under '{analysis_name}'.")
        return

    print(f"--- Starting Group Analysis: {analysis_name} / {args.group_model} ---")

    output_dir = os.path.join(config["output_dir"], "group_analysis", analysis_name, args.group_model)
    os.makedirs(output_dir, exist_ok=True)

    # --- Subject and Mask Generation ---
    all_subjects_info = config.get("subjects", [])
    group_model_subjects = group_model_config.get("groups")
    
    subjects_to_process = [s for s in all_subjects_info if s["group"] in group_model_subjects]
    
    mask_files = []
    for sub_info in subjects_to_process:
        for ses_id in group_model_config.get("sessions", []):
            mask_path = os.path.join(config["output_dir"], sub_info["id"], f"ses-{ses_id}", "func_preproc", f"{sub_info['id']}_preproc.results", f"mask_epi_anat.{sub_info['id']}_preproc+tlrc.HEAD")
            if os.path.exists(mask_path):
                mask_files.append(mask_path.replace(".HEAD", ""))
            else:
                print(f"Warning: Mask file not found, skipping: {mask_path}")
    
    if not mask_files:
        print("Error: No mask files found for any subjects. Aborting.")
        return

    group_mask_path = os.path.join(output_dir, "group_mask")
    subprocess.run([
        "3dmask_tool",
        "-input"] + mask_files + [
        "-prefix", group_mask_path,
        "-frac", "0.5"
    ], check=True)

    # --- Analysis-specific logic ---
    analysis_type = group_model_config["type"]
    script_path = os.path.join("scripts", "04_run_group_analysis.sh")
    
    command = [
        "bash", script_path,
        "--type", analysis_type,
        "--output_prefix", os.path.join(output_dir, f"result_{args.group_model}"),
        "--mask", f"{group_mask_path}+tlrc",
    ]

    if analysis_type == "3dLMEr":
        # Generate data table
        data_table_path = os.path.join(output_dir, "data_table.txt")
        model_factors = group_model_config["model"].split("*")
        header = "Sub" + "\t".join(f.split("(")[0] for f in model_factors if "+" not in f) + "\tInputFile\n"
        
        with open(data_table_path, "w") as f:
            f.write(header)
            for sub_info in subjects_to_process:
                for ses_id in group_model_config.get("sessions", []):
                    for i, contrast in enumerate(group_model_config["contrasts"]):
                        stats_file = os.path.join(
                            config["output_dir"], sub_info["id"], f"ses-{ses_id}", "glm", analysis_name,
                            f"{sub_info['id']}_{analysis_name}.results",
                            f"stats.{sub_info['id']}_{analysis_name}+tlrc[{contrast}]"
                        )
                        if not os.path.exists(stats_file.split("[")[0] + ".HEAD"):
                            print(f"Warning: Stats file not found, skipping: {stats_file}")
                            continue
                        
                        line = f"{sub_info['id']}\t"
                        if "session" in header:
                            line += f"ses-{ses_id}\t"
                        if "group" in header:
                            line += f"{sub_info['group']}\t"
                        line += f"{group_model_config['stimulus_labels'][i]}\t"
                        line += f"{stats_file}\n"
                        f.write(line)
        
        # Format GLT codes
        glt_codes = " ".join([f"-gltCode {g['label']} \'{g['sym']}\'" for g in group_model_config["glt"]])

        command.extend([
            "--data_table", data_table_path,
            "--model", group_model_config["model"],
            "--glt_codes", glt_codes
        ])

    elif analysis_type == "3dttest++":
        setA_label = group_model_config.get("setA_label")
        contrast_name = group_model_config.get("contrast")
        if not setA_label or not contrast_name:
            print("Error: 3dttest++ requires 'setA_label' and 'contrast' in config.")
            return

        setA_files = []
        for sub_info in subjects_to_process:
            for ses_id in group_model_config.get("sessions", []):
                stats_file = os.path.join(
                    config["output_dir"], sub_info["id"], f"ses-{ses_id}", "glm", analysis_name,
                    f"{sub_info['id']}_{analysis_name}.results",
                    f"stats.{sub_info['id']}_{analysis_name}+tlrc[{contrast_name}]"
                )
                if not os.path.exists(stats_file.split("[")[0] + ".HEAD"):
                    print(f"Warning: Stats file not found, skipping: {stats_file}")
                    continue
                
                setA_files.append(sub_info['id'])
                setA_files.append(f"{stats_file}")

        command.extend([
            "--setA_label", setA_label,
            "--setA_files", " ".join(setA_files)
        ])

    # --- Execute ---
    log_file_path = os.path.join("logs", f"group_analysis_{analysis_name}_{args.group_model}.log")
    print(f"Executing group analysis. Check log for details: {log_file_path}")
    
    with open(log_file_path, "w") as log_file:
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, cwd=output_dir)
        process.wait()

    if process.returncode == 0:
        print(f"Successfully completed group analysis. Results in: {output_dir}")
    else:
        print(f"Error running group analysis. Check log: {log_file_path}")


def main():
    """Main function to run the analysis pipeline."""
    parser = argparse.ArgumentParser(description="fMRI Analysis Pipeline Runner for WAR task")
    parser.add_argument("--subject", help="Specify a single subject ID to process (e.g., sub-AL01). Overrides subject lists in configs.")
    parser.add_argument("--analysis", nargs='*', help="Specify one or more analysis models to run for 'glm', 'all', or 'group_analysis' step.")
    parser.add_argument("--step", choices=["preprocess", "create_timings", "preprocess_anat", "preprocess_func", "glm", "all", "group_analysis"], required=True, help="The processing step to execute.")
    parser.add_argument("--session", help="Specify the session number (e.g., 1). If not provided, all sessions for the subject(s) will be processed.")
    parser.add_argument("--n_procs", type=int, default=1, help="Number of subjects to process in parallel.")
    parser.add_argument("--group_model", help="Specify the group analysis model name to run (required for 'group_analysis' step).")


    args = parser.parse_args()

    try:
        main_config = toml.load("analysis_configs/main_config.toml")
        analysis_models = toml.load("analysis_configs/analysis_models.toml")
    except FileNotFoundError as e:
        print(f"Error: Configuration file not found. {e}")
        return

    if args.step == "group_analysis":
        run_group_analysis(args, main_config, analysis_models)
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
