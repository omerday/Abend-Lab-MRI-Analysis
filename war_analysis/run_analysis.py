import argparse
import os
import subprocess
import json
import toml
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich import print as rprint
from rich.traceback import install

# Install rich traceback handler
install()

console = Console()

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
        console.log(f"[bold red]Error:[/] Invalid step name '{step_name}'")
        return False

    script_path = os.path.join("scripts", script_name)
    if not os.path.exists(script_path):
        console.log(f"[bold red]Error:[/] Script not found at {script_path}")
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

    console.log(f"[dim]Executing for {subject}: {' '.join(command)}[/]")

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
        console.log(f"[green]✓ {step_name}[/] completed for [bold]{subject}[/]")
        return True
    else:
        console.log(f"[bold red]✖ {step_name}[/] failed for [bold]{subject}[/]. See log: [underline]{log_file_path}[/]")
        return False

def process_subject(subject_id, args, main_config, analysis_models, progress=None, task_id=None):
    """Runs the requested pipeline steps for a single subject."""
    # Find subject-specific config
    subject_config = next((s for s in main_config.get("subjects", []) if s.get("id") == subject_id), None)
    if not subject_config:
        console.log(f"[yellow]Warning:[/] Subject {subject_id} configuration not found. Skipping.")
        return

    sessions_to_process_configs = []
    if args.session:
        try:
            session_id_to_find = int(args.session)
            session_config = next((ses for ses in subject_config.get("sessions", []) if ses.get("id") == session_id_to_find), None)
            if not session_config:
                console.log(f"[red]Error:[/] Session '{args.session}' not found for {subject_id}. Aborting.")
                return
            sessions_to_process_configs.append(session_config)
        except ValueError:
            console.log(f"[red]Error:[/] --session must be an integer. Got '{args.session}'.")
            return
    else:
        sessions_to_process_configs = subject_config.get("sessions", [])
        if not sessions_to_process_configs:
            console.log(f"[yellow]Warning:[/] No sessions found for {subject_id}. Skipping.")
            return

    for session_config in sessions_to_process_configs:
        session_id_str = str(session_config["id"])
        
        # Determine steps to run
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
                    console.log(f"[yellow]Warning:[/] Analysis model '{analysis_name}' not found.")

        lag_block_1 = session_config.get("lag_block_1", 0)
        lag_block_2 = session_config.get("lag_block_2", 0)

        for step in steps_to_run:
            if progress and task_id:
                progress.update(task_id, description=f"[cyan]{subject_id}[/] - {step}")

            extra_args = None
            if step == 'create_timings':
                extra_args = ["--lag_block_1", str(lag_block_1), "--lag_block_2", str(lag_block_2)]

            if step == 'glm':
                if not analysis_names:
                    console.log(f"[red]Error:[/] --analysis is required for 'glm' step.")
                    break

                all_glm_success = True
                for analysis_name in analysis_names:
                    analysis_model_config = analysis_models.get(analysis_name, {})
                    requires_scr = analysis_model_config.get("requires_scr", False)
                    session_has_scr = session_config.get("has_scr", False)

                    if requires_scr and not session_has_scr:
                        console.log(f"[dim]Skipping '{analysis_name}' for {subject_id} (No SCR data)[/]")
                        continue
                    
                    if progress and task_id:
                        progress.update(task_id, description=f"[cyan]{subject_id}[/] - glm: {analysis_name}")

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
                    console.log(f"[red]Stopping pipeline for {subject_id} because a GLM step failed.[/]")
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
                    console.log(f"[red]Stopping pipeline for {subject_id} because '{step}' failed.[/]")
                    break
    
    if progress and task_id:
        progress.update(task_id, advance=1)

def run_group_analysis(args, config, analysis_models):
    """Runs a specified group-level analysis."""
    console.print(Panel(f"Group Analysis: [bold cyan]{args.group_model}[/]", style="bold blue"))

    if not args.analysis or len(args.analysis) > 1:
        console.log("[red]Error:[/] Please specify exactly one first-level analysis model using --analysis.")
        return
    analysis_name = args.analysis[0]

    if not args.group_model:
        console.log("[red]Error:[/] Please specify a group analysis model using --group_model.")
        return

    f_level_model = analysis_models.get(analysis_name)
    if not f_level_model:
        console.log(f"[red]Error:[/] First-level analysis '{analysis_name}' not found.")
        return

    group_model_config = next((g for g in f_level_model.get("group_analyses", []) if g["name"] == args.group_model), None)
    if not group_model_config:
        console.log(f"[red]Error:[/] Group analysis model '{args.group_model}' not found under '{analysis_name}'.")
        return

    output_dir = os.path.join(config["output_dir"], "group_analysis", analysis_name, args.group_model)
    os.makedirs(output_dir, exist_ok=True)

    # --- Subject and Mask Generation ---
    all_subjects_info = config.get("subjects", [])
    subjects_to_process = []

    if "subjects" in group_model_config:
        custom_subjects = group_model_config["subjects"]
        subjects_ids_to_include = []

        if isinstance(custom_subjects, list):
            subjects_ids_to_include = custom_subjects
            console.log(f"Using custom list of {len(subjects_ids_to_include)} subjects.")
        elif isinstance(custom_subjects, dict):
            console.log(f"Using custom subject lists per group.")
            valid_groups = group_model_config.get("groups", [])
            for group_name, subject_list in custom_subjects.items():
                if group_name not in valid_groups:
                    continue
                subjects_ids_to_include.extend(subject_list)
        
        subject_id_map = {s['id']: s for s in all_subjects_info}
        for sub_id in subjects_ids_to_include:
            if sub_id in subject_id_map:
                subjects_to_process.append(subject_id_map[sub_id])
            else:
                console.log(f"[yellow]Warning:[/] Subject '{sub_id}' from custom list not found.")

    else:
        group_model_groups = group_model_config.get("groups")
        console.log(f"Using all subjects from group(s): {group_model_groups}")
        subjects_to_process = [s for s in all_subjects_info if s["group"] in group_model_groups]

    if not subjects_to_process:
        console.log("[red]Error:[/] No subjects to process after filtering.")
        return
    
    mask_files = []
    for sub_info in subjects_to_process:
        for ses_id in group_model_config.get("sessions", []):
            mask_path = os.path.join(config["output_dir"], sub_info["id"], f"ses-{ses_id}", "func_preproc", f"{sub_info['id']}_preproc.results", f"mask_epi_anat.{sub_info['id']}_preproc+tlrc.HEAD")
            if os.path.exists(mask_path):
                mask_files.append(mask_path.replace(".HEAD", ""))
            else:
                console.log(f"[yellow]Warning:[/] Mask file not found: {mask_path}")
    
    if not mask_files:
        console.log("[red]Error:[/] No mask files found.")
        return

    group_mask_path = os.path.join(output_dir, "group_mask")
    subprocess.run([
        "3dmask_tool",
        "-input"] + mask_files + [
        "-prefix", group_mask_path,
        "-frac", "0.4",
        "-overwrite"
    ], check=True)

    # --- Analysis-specific logic ---
    analysis_type = group_model_config["type"]
    script_path = os.path.abspath(os.path.join("scripts", "04_run_group_analysis.sh"))
    
    command = [
        "bash", script_path,
        "--type", analysis_type,
        "--output_prefix", os.path.join(output_dir, f"result_{args.group_model}"),
        "--mask", f"{group_mask_path}+tlrc",
    ]

    if analysis_type == "3dLMEr":
        table_columns = group_model_config.get("table_columns", [])
        if not table_columns:
            console.log(f"[red]Error:[/] 'table_columns' is missing in config.")
            return
        header_columns = ["Subj"] + table_columns + ["InputFile"]
        header = "\t".join(header_columns) + "\n"

        data_table_path = os.path.join(output_dir, "data_table.txt")
        
        if "data_table_rows" not in group_model_config:
            console.log(f"[red]Error:[/] 'data_table_rows' is missing in config.")
            return

        with open(data_table_path, "w") as f:
            f.write(header)
            
            for sub_info in subjects_to_process:
                for ses_id in group_model_config.get("sessions", []):
                    for row_def in group_model_config["data_table_rows"]:
                        contrast_name = row_def["contrast"]
                        
                        stats_file = os.path.join(
                            config["output_dir"], sub_info["id"], f"ses-{ses_id}", "glm", analysis_name,
                            f"{sub_info['id']}_{analysis_name}.results",
                            f"stats.{sub_info['id']}_{analysis_name}+tlrc[{contrast_name}]"
                        )
                        if not os.path.exists(stats_file.split("[")[0] + ".HEAD"):
                            console.log(f"[yellow]Warning:[/] Stats file not found: {stats_file}")
                            continue
                        
                        row_data = {
                            "Subj": sub_info['id'],
                            "session": f"ses-{ses_id}",
                            "group": sub_info.get('group', 'NA'),
                            "InputFile": stats_file
                        }
                        
                        for key, value in row_def.items():
                            if key != 'contrast':
                                row_data[key] = value

                        line_parts = [str(row_data.get(col_name, "NA")) for col_name in header_columns]
                        line = "\t".join(line_parts) + "\n"
                        f.write(line)
        
        glt_codes = " ".join([f"-gltCode {g['label']} \"{g['sym']}\"" for g in group_model_config["glt"]])

        command.extend([
            "--data_table", data_table_path,
            "--model", group_model_config["model"],
            "--glt_codes", glt_codes
        ])

    elif analysis_type == "3dttest++":
        setA_label = group_model_config.get("setA_label")
        contrast_name = group_model_config.get("contrast")
        if not setA_label or not contrast_name:
            console.log("[red]Error:[/] 3dttest++ requires 'setA_label' and 'contrast'.")
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
                    console.log(f"[yellow]Warning:[/] Stats file not found: {stats_file}")
                    continue
                
                setA_files.append(sub_info['id'])
                setA_files.append(f"{stats_file}")

        command.extend([
            "--setA_label", setA_label,
            "--setA_files", " ".join(setA_files)
        ])

    log_file_path = os.path.join("logs", f"group_analysis_{analysis_name}_{args.group_model}.log")
    console.log(f"[dim]Executing group analysis. See log: {log_file_path}[/]")
    
    with open(log_file_path, "w") as log_file:
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, cwd=output_dir)
        process.wait()

    if process.returncode == 0:
        console.log(f"[bold green]SUCCESS:[/] Group analysis complete. Results in: {output_dir}")
    else:
        console.log(f"[bold red]ERROR:[/] Group analysis failed. Check log: {log_file_path}")


def main():
    """Main function to run the analysis pipeline."""
    parser = argparse.ArgumentParser(description="fMRI Analysis Pipeline Runner for WAR task")
    parser.add_argument("--subject", nargs='*', help="Specify subject IDs to process (e.g., sub-AL01). Overrides subject lists in configs.")
    parser.add_argument("--analysis", nargs='*', help="Specify one or more analysis models to run for 'glm', 'all', or 'group_analysis' step.")
    parser.add_argument("--step", choices=["preprocess", "create_timings", "preprocess_anat", "preprocess_func", "glm", "all", "group_analysis"], required=True, help="The processing step to execute.")
    parser.add_argument("--session", help="Specify the session number (e.g., 1). If not provided, all sessions for the subject(s) will be processed.")
    parser.add_argument("--n_procs", type=int, default=1, help="Number of subjects to process in parallel.")
    parser.add_argument("--group_model", help="Specify the group analysis model name to run (required for 'group_analysis' step).")

    args = parser.parse_args()

    console.print(Panel(f"fMRI Analysis Pipeline\n[dim]Step: {args.step}[/]", style="bold blue"))

    try:
        main_config = json.loads(json.dumps(toml.load("analysis_configs/main_config.toml")))
        analysis_models = json.loads(json.dumps(toml.load("analysis_configs/analysis_models.toml")))
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/] Configuration file not found. {e}")
        return

    if args.step == "group_analysis":
        run_group_analysis(args, main_config, analysis_models)
        return

    subjects_to_process_ids = []
    if args.subject:
        subjects_to_process_ids = [subj for subj in args.subject]
    elif args.analysis and args.step in ["glm", "all"]:
        first_analysis = args.analysis[0]
        model = analysis_models.get(first_analysis, {})
        if "subjects" in model: 
            subjects_to_process_ids = model["subjects"]
        else:
            subjects_to_process_ids = [s["id"] for s in main_config.get("subjects", [])]
    else:
        subjects_to_process_ids = [s["id"] for s in main_config.get("subjects", [])]

    if not subjects_to_process_ids:
        console.print("[yellow]No subjects found to process. Check your configuration.[/]")
        return

    if args.analysis:
        for analysis_name in args.analysis:
            if analysis_name not in analysis_models:
                console.print(f"[bold red]Error:[/] Analysis model '{analysis_name}' not found.")
                return
    
    console.print(f"Processing [bold cyan]{len(subjects_to_process_ids)}[/] subjects.")
    
    # Using Rich Progress Bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        
        main_task = progress.add_task("[green]Overall Progress", total=len(subjects_to_process_ids))
        
        if args.n_procs > 1 and len(subjects_to_process_ids) > 1:
            # We can't update rich progress easily from subprocesses without a Manager, 
            # so for parallel processing, we might lose the granular progress bar updates per subject
            # unless we use something like rich.progress.track for the main loop only.
            # For simplicity in this implementation, if n_procs > 1, we just run the loop but lose the detailed
            # inside-function progress updates, or we switch to sequential if we want pretty bars.
            # Let's keep it sequential for the rich demo if the user didn't ask for massive parallel speed,
            # OR we can just wrap the executor map.
            
            console.log(f"[yellow]Parallel processing with {args.n_procs} cores enabled. Detailed progress bars might be simplified.[/]")
            
            worker_func = partial(process_subject, args=args, main_config=main_config, analysis_models=analysis_models, progress=None, task_id=None)
            
            with ProcessPoolExecutor(max_workers=args.n_procs) as executor:
                # We map the function and manually update the main bar as they finish
                futures = [executor.submit(worker_func, sub_id) for sub_id in subjects_to_process_ids]
                for future in futures:
                    future.result() # Wait for each
                    progress.update(main_task, advance=1)
        else:
            # Sequential processing allows us to pass the progress object down
            for subject_id in subjects_to_process_ids:
                process_subject(subject_id, args, main_config, analysis_models, progress, main_task)

    console.print(Panel("[bold green]All processing complete[/]", style="green"))

if __name__ == "__main__":
    main()
