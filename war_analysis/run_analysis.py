"""Main analysis controller and CLI runner for the WAR pipeline.

Orchestrates first-level neuroimaging workflow steps (timing generation,
anatomical SSW normalization, multi-echo functional preprocessing, and
first-level GLM regression) and group-level statistical models (3dttest++, 3dLMEr)
for the Threat Appraisal and Regulation (WAR) task paradigm.

AFNI Neuroimaging Parameters & Rationale:
  - Repetition Time (TR = 2.0s): Discrete functional sampling rate (Nyquist 0.25 Hz),
    matching behavioral blocks (22s = 11 TRs) and image presentations (4s = 2 TRs).
  - WAR Paradigm Specifics: 28-second initial lag period (14 TRs deducted, yielding
    286 TRs vs 300 TRs) and 11-bin block expansion (t, t+2, ..., t+20) for continuous
    autonomic skin conductance response (SCR) modeling.
  - Multi-Echo Echo Times (13.6, 25.96, 38.3 ms) & Optimal Combination (OC):
    Estimates voxel-wise T2* decay to combine echoes, recovering signal in
    susceptibility dropout zones (amygdala, vmPFC) and maximizing CNR.
  - Anatomical Normalization (sswarper2): Non-linear warping to MNI152_2009
    using Local Pearson Correlation (-cost_nl_final lpa), -giant_move, and
    -minp 8 for robust subcortical alignment under B1 field inhomogeneities.
  - Spatial Smoothing (4.0 mm FWHM): Isotropic Gaussian kernel preserving fine
    subcortical boundaries (basolateral amygdala, BNST) without signal bleed.
  - Motion Censoring (0.5 mm): Euclidean norm (enorm) threshold scrubbed to
    prevent motion-induced false positives in emotional contrasts.
  - Outlier Censoring (0.05): Scrubs volumes where >5% of automasked voxels
    are 3dToutcount outliers.
  - Intermediate Storage Optimization (KEEP_PB00_PB04): Purges pb00-pb04
    bricks while preserving pb05.scale, fitts, errts, motion, and stats.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Union

try:
    import toml
except ImportError:
    import tomllib as toml  # type: ignore

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.traceback import install

# Add repository root and pipeline directory to sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

try:
    from export_results import export_subject_results
except ImportError:
    export_subject_results = None  # type: ignore

from cloud.gcs_helper import (
    cleanup_pb00_to_pb04,
    gcs_download_wildcard,
    gcs_sync_down,
    gcs_sync_up,
    gcs_upload_file,
    is_gcs_uri,
    join_uri,
    shard_subjects_for_cloud_task,
    stage_in_subject_input,
)

# Install rich traceback handler
install()

console = Console()


def expand_steps(step_args: Union[str, List[str]]) -> List[str]:
    """Expand composite step names ('preprocess', 'all') and deduplicate while preserving execution order.

    Supports e.g. `--step preprocess glm` or `--step all`.

    Args:
        step_args: Single step string or list of step strings.

    Returns:
        Expanded, ordered list of concrete individual step names.
    """
    if isinstance(step_args, str):
        step_args = [step_args]

    expanded: List[str] = []
    for s in step_args:
        if s == "all":
            seq = ["create_timings", "preprocess_anat", "preprocess_func", "glm"]
        elif s == "preprocess":
            seq = ["create_timings", "preprocess_anat", "preprocess_func"]
        else:
            seq = [s]
        for item in seq:
            if item not in expanded:
                expanded.append(item)
    return expanded


def stage_in_prerequisites(
    subject_id: str,
    session_id_str: str,
    step_name: str,
    config: Dict[str, Any],
    active_output_dir: str,
    active_input_dir: Optional[str],
) -> None:
    """Ensure required prerequisite datasets exist in active working/scratch directory.

    If missing locally, stages them in from the permanent output directory (local or GCS).

    Args:
        subject_id: Subject identifier string (e.g. 'sub-MD01').
        session_id_str: Numerical or string session identifier (e.g. '1').
        step_name: Current step name ('preprocess_func', 'glm', etc.).
        config: Parsed main_config dictionary.
        active_output_dir: Active output scratch directory path.
        active_input_dir: Active input directory path.
    """
    perm_output_root = config["output_dir"]
    if active_output_dir == perm_output_root and not is_gcs_uri(perm_output_root):
        return

    session_prefix = f"ses-{session_id_str}"
    local_session_dir = os.path.join(active_output_dir, subject_id, session_prefix)
    perm_session_dir = join_uri(perm_output_root, subject_id, session_prefix)

    # 1. Preprocess Func requires 'anat_warped' from preprocess_anat
    if step_name == "preprocess_func":
        local_anat = os.path.join(local_session_dir, "anat_warped")
        perm_anat = join_uri(perm_session_dir, "anat_warped")

        if not os.path.exists(local_anat) or not os.listdir(local_anat):
            if is_gcs_uri(perm_output_root):
                console.log(f"[dim]Staging in anat_warped from GCS for {subject_id} ({session_prefix})...[/]")
                if not gcs_sync_down(perm_anat, local_anat):
                    console.log(f"[yellow]Warning:[/] Pre-requisite anat_warped not found in GCS at: {perm_anat}")
            elif os.path.exists(perm_anat):
                console.log(f"[dim]Staging in anat_warped from permanent output for {subject_id} ({session_prefix})...[/]")
                os.makedirs(local_anat, exist_ok=True)
                subprocess.run(["rsync", "-a", f"{perm_anat}/", f"{local_anat}/"], check=True)
            else:
                console.log(f"[yellow]Warning:[/] Pre-requisite anat_warped not found on permanent drive at: {perm_anat}")

    # 2. GLM requires 'func_preproc' results from preprocess_func and 'timings' from create_timings
    elif step_name == "glm":
        local_func = os.path.join(local_session_dir, "func_preproc")
        local_func_results = os.path.join(local_func, f"{subject_id}_preproc.results")
        perm_func = join_uri(perm_session_dir, "func_preproc")

        if not os.path.exists(local_func_results) or not os.listdir(local_func_results):
            if is_gcs_uri(perm_output_root):
                console.log(f"[dim]Staging in func_preproc from GCS for {subject_id} ({session_prefix})...[/]")
                if not gcs_sync_down(perm_func, local_func):
                    console.log(f"[yellow]Warning:[/] Pre-requisite func_preproc not found in GCS at: {perm_func}")
            elif os.path.exists(perm_func):
                console.log(f"[dim]Staging in func_preproc from permanent output for {subject_id} ({session_prefix})...[/]")
                os.makedirs(local_func, exist_ok=True)
                subprocess.run(["rsync", "-a", f"{perm_func}/", f"{local_func}/"], check=True)
            else:
                console.log(f"[yellow]Warning:[/] Pre-requisite func_preproc not found on permanent drive at: {perm_func}")

        # Ensure timings exist locally
        local_input_timings = (
            os.path.join(active_input_dir, subject_id, session_prefix, "func", "timings")
            if active_input_dir
            else ""
        )
        local_output_timings = os.path.join(local_session_dir, "timings")
        perm_timings = join_uri(perm_session_dir, "timings")

        has_input_timings = os.path.exists(local_input_timings) and bool(os.listdir(local_input_timings))
        has_output_timings = os.path.exists(local_output_timings) and bool(os.listdir(local_output_timings))

        if not has_input_timings and not has_output_timings:
            if is_gcs_uri(perm_output_root):
                console.log(f"[dim]Staging in timings from GCS for {subject_id} ({session_prefix})...[/]")
                gcs_sync_down(perm_timings, local_output_timings)
            elif os.path.exists(perm_timings):
                os.makedirs(local_output_timings, exist_ok=True)
                subprocess.run(["rsync", "-a", f"{perm_timings}/", f"{local_output_timings}/"], check=True)


def stage_out_step(
    subject_id: str,
    session_id_str: str,
    step_name: str,
    config: Dict[str, Any],
    active_output_dir: str,
    active_input_dir: Optional[str] = None,
    analysis_name: Optional[str] = None,
) -> None:
    """Sync specific step output directory from scratch back to permanent storage or GCS.

    Args:
        subject_id: Subject identifier.
        session_id_str: Session identifier string.
        step_name: Name of completed step.
        config: Parsed main configuration.
        active_output_dir: Active output scratch directory.
        active_input_dir: Optional active input scratch directory.
        analysis_name: Model name for GLM steps.
    """
    perm_output_root = config["output_dir"]
    session_prefix = f"ses-{session_id_str}"

    if step_name == "create_timings":
        if not active_input_dir:
            return
        local_timings = os.path.join(active_input_dir, subject_id, session_prefix, "func", "timings")
        if not os.path.exists(local_timings):
            return
        perm_timings = join_uri(perm_output_root, subject_id, session_prefix, "timings")
        if is_gcs_uri(perm_output_root):
            console.log(f"[cyan]Syncing {subject_id} ({session_prefix}) [timings] to GCS...[/]")
            gcs_sync_up(local_timings, perm_timings)
        elif active_output_dir != perm_output_root:
            os.makedirs(perm_timings, exist_ok=True)
            subprocess.run(["rsync", "-av", "--update", f"{local_timings}/", f"{perm_timings}/"], check=True)
        return

    if active_output_dir == perm_output_root and not is_gcs_uri(perm_output_root):
        return

    if step_name == "preprocess_anat":
        subfolder = os.path.join(subject_id, session_prefix, "anat_warped")
    elif step_name == "preprocess_func":
        subfolder = os.path.join(subject_id, session_prefix, "func_preproc")
    elif step_name == "glm" and analysis_name:
        subfolder = os.path.join(subject_id, session_prefix, "glm", analysis_name)
    else:
        return

    local_path = os.path.join(active_output_dir, subfolder)
    perm_path = join_uri(perm_output_root, subfolder.replace(os.sep, "/"))

    if os.path.exists(local_path):
        if step_name == "preprocess_func" and not config.get("keep_pb00_pb04", False):
            cleanup_pb00_to_pb04(local_path, subject_id, console=console)

        label = f"{step_name}" if step_name != "glm" else f"glm: {analysis_name}"
        label_str = escape(f"[{label}]")

        if is_gcs_uri(perm_output_root):
            console.log(f"[cyan]Uploading {subject_id} ({session_prefix}) [{label}] output to GCS ({perm_path})...[/]")
            gcs_sync_up(local_path, perm_path)
            if step_name == "glm" and config.get("cleanup_scratch", True):
                shutil.rmtree(local_path, ignore_errors=True)
        else:
            os.makedirs(perm_path, exist_ok=True)
            console.log(f"[cyan]Syncing {subject_id} ({session_prefix}) {label_str} output to permanent drive...[/]")
            subprocess.run(["rsync", "-av", "--update", f"{local_path}/", f"{perm_path}/"], check=True)


def cleanup_subject_scratch(
    subject_id: str,
    active_output_dir: str,
    active_input_dir: Optional[str],
    config: Dict[str, Any],
) -> None:
    """Clean up local scratch folders for subject if configured."""
    if not config.get("cleanup_scratch", True):
        return

    if active_output_dir != config["output_dir"] or is_gcs_uri(config["output_dir"]):
        local_sub_out = os.path.join(active_output_dir, subject_id)
        if os.path.exists(local_sub_out):
            console.log(f"[dim]Cleaning local output scratch for {subject_id}...[/]")
            shutil.rmtree(local_sub_out, ignore_errors=True)

    if active_input_dir and active_input_dir != config["input_dir"]:
        local_sub_in = os.path.join(active_input_dir, subject_id)
        if os.path.exists(local_sub_in):
            console.log(f"[dim]Cleaning local input scratch for {subject_id}...[/]")
            shutil.rmtree(local_sub_in, ignore_errors=True)


def run_step(
    subject: str,
    session: str,
    active_input_dir: str,
    config: Dict[str, Any],
    analysis_name: Optional[str],
    step_name: str,
    active_output_dir: str,
    extra_args: Optional[List[str]] = None,
) -> bool:
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

    base_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(base_dir, "scripts", script_name)
    if not os.path.exists(script_path):
        console.log(f"[bold red]Error:[/] Script not found at {script_path}")
        return False

    command = [
        "bash", script_path,
        "--subject", subject,
        "--session", session,
        "--input", active_input_dir,
    ]

    if step_name != "create_timings":
        command.extend(["--output", active_output_dir])

    if analysis_name and step_name == "glm":
        command.extend(["--analysis", analysis_name])

    if extra_args:
        command.extend(extra_args)

    console.log(f"[dim]Executing for {subject}: {' '.join(command)}[/]")

    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_name_parts = [subject, step_name]
    if analysis_name and step_name == "glm":
        log_name_parts.append(analysis_name)
    log_filename = f"{'_'.join(log_name_parts)}.log"
    log_file_path = os.path.join(log_dir, log_filename)

    env = os.environ.copy()
    if config.get("keep_pb00_pb04", False):
        env["KEEP_PB00_PB04"] = "1"

    stream_live = is_gcs_uri(config.get("output_dir")) or os.environ.get("STREAM_STEP_LOGS") == "1"

    try:
        with open(log_file_path, "w") as log_file:
            if stream_live:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    universal_newlines=True,
                    bufsize=1,
                )
                if process.stdout:
                    for line in process.stdout:
                        log_file.write(line)
                        log_file.flush()
                        sys.stdout.write(f"[{subject}|{step_name}] {line}")
                        sys.stdout.flush()
                process.wait()
            else:
                process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, env=env)
                process.wait()
    finally:
        if is_gcs_uri(config.get("output_dir")) and os.path.exists(log_file_path):
            gcs_log_uri = join_uri(config["output_dir"], "logs", log_filename)
            gcs_upload_file(log_file_path, gcs_log_uri)

    if process.returncode == 0:
        console.log(f"[green]✓ {step_name}[/] completed for [bold]{subject}[/]")
        return True

    console.log(f"[bold red]✖ {step_name}[/] failed for [bold]{subject}[/]. See log: [underline]{log_file_path}[/]")
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r", errors="replace") as lf:
                tail_lines = lf.readlines()[-30:]
            console.log("[red]--- Last 30 lines of step log ---[/]\n" + "".join(tail_lines))
        except Exception:
            pass
    return False


def process_subject(
    subject_id: str,
    args: argparse.Namespace,
    main_config: Dict[str, Any],
    analysis_models: Dict[str, Any],
    progress: Optional[Any] = None,
    task_id: Optional[Any] = None,
) -> bool:
    """Runs the requested pipeline steps for a single WAR subject.

    Returns:
        bool: True if all requested sessions and steps completed successfully,
              False if any step, staging, or validation failed.
    """
    use_scratch = not getattr(args, "no_scratch", False)
    scratch_root = getattr(args, "scratch_dir", None) or main_config.get("scratch_dir", "/tmp/afni_scratch")

    if is_gcs_uri(main_config["output_dir"]) or (use_scratch and scratch_root):
        active_output_dir = os.path.join(scratch_root, "output") if is_gcs_uri(main_config["output_dir"]) else scratch_root
    else:
        active_output_dir = main_config["output_dir"]

    os.makedirs(active_output_dir, exist_ok=True)

    subject_config = next((s for s in main_config.get("subjects", []) if s.get("id") == subject_id), None)
    if not subject_config:
        console.log(f"[yellow]Warning:[/] Subject {subject_id} configuration not found. Skipping.")
        return False

    sessions_to_process_configs = []
    if args.session:
        try:
            session_id_to_find = int(args.session)
            session_config = next((ses for ses in subject_config.get("sessions", []) if ses.get("id") == session_id_to_find), None)
            if not session_config:
                console.log(f"[red]Error:[/] Session '{args.session}' not found for {subject_id}. Aborting.")
                return False
            sessions_to_process_configs.append(session_config)
        except ValueError:
            console.log(f"[red]Error:[/] --session must be an integer. Got '{args.session}'.")
            return False
    else:
        sessions_to_process_configs = subject_config.get("sessions", [])
        if not sessions_to_process_configs:
            console.log(f"[yellow]Warning:[/] No sessions found for {subject_id}. Skipping.")
            return False

    active_input_dir = None
    try:
        steps_to_run = expand_steps(args.step)

        needs_raw_input = any(s in steps_to_run for s in ["create_timings", "preprocess_anat", "preprocess_func"])
        if needs_raw_input or is_gcs_uri(main_config["input_dir"]):
            try:
                active_input_dir = stage_in_subject_input(
                    subject_id=subject_id,
                    configured_input_dir=main_config["input_dir"],
                    scratch_root=scratch_root,
                    console=console,
                )
            except FileNotFoundError as exc:
                if needs_raw_input:
                    console.log(f"[bold red]Error staging input for {subject_id}:[/] {exc}")
                    return False
                active_input_dir = os.path.join(scratch_root, "input")
        else:
            active_input_dir = main_config["input_dir"]

        for session_config in sessions_to_process_configs:
            session_id_str = str(session_config["id"])

            analysis_names = args.analysis
            if (not analysis_names or analysis_names == ["all"]) and "glm" in steps_to_run:
                analysis_names = list(analysis_models.keys())

            if analysis_names and "glm" in steps_to_run:
                for analysis_name in analysis_names:
                    if analysis_name not in analysis_models:
                        console.log(f"[yellow]Warning:[/] Analysis model '{analysis_name}' not found.")

            lag_block_1 = session_config.get("lag_block_1", 0)
            lag_block_2 = session_config.get("lag_block_2", 0)

            for step in steps_to_run:
                if progress and task_id:
                    progress.update(task_id, description=f"[cyan]{subject_id}[/] - {step}")

                if active_output_dir != main_config["output_dir"] or is_gcs_uri(main_config["output_dir"]):
                    stage_in_prerequisites(
                        subject_id, session_id_str, step, main_config, active_output_dir, active_input_dir
                    )

                extra_args = None
                if step == "create_timings":
                    extra_args = ["--lag_block_1", str(lag_block_1), "--lag_block_2", str(lag_block_2)]

                if step == "glm":
                    if not analysis_names:
                        console.log("[red]Error:[/] --analysis is required for 'glm' step.")
                        return False

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
                            active_input_dir=active_input_dir,
                            config=main_config,
                            analysis_name=analysis_name,
                            step_name=step,
                            active_output_dir=active_output_dir,
                            extra_args=extra_args,
                        )
                        if not success:
                            console.log(f"[red]Stopping pipeline for {subject_id} because GLM step '{analysis_name}' failed.[/]")
                            return False

                        stage_out_step(
                            subject_id,
                            session_id_str,
                            "glm",
                            main_config,
                            active_output_dir,
                            active_input_dir=active_input_dir,
                            analysis_name=analysis_name,
                        )
                else:
                    success = run_step(
                        subject=subject_id,
                        session=session_id_str,
                        active_input_dir=active_input_dir,
                        config=main_config,
                        analysis_name=None,
                        step_name=step,
                        active_output_dir=active_output_dir,
                        extra_args=extra_args,
                    )
                    if not success:
                        console.log(f"[red]Stopping pipeline for {subject_id} because '{step}' failed.[/]")
                        return False

                    stage_out_step(
                        subject_id,
                        session_id_str,
                        step,
                        main_config,
                        active_output_dir,
                        active_input_dir=active_input_dir,
                    )

        return True
    except Exception as exc:
        console.log(f"[bold red]Unexpected error processing {subject_id}:[/] {exc}")
        return False
    finally:
        cleanup_subject_scratch(subject_id, active_output_dir, active_input_dir, main_config)


def _stage_group_subject_files(
    config: Dict[str, Any],
    scratch_root: str,
    sub_id: str,
    ses_id: Any,
    analysis_name: str,
) -> str:
    """For group_analysis on GCS, selectively download mask and stats files into local scratch."""
    perm_output = config["output_dir"]
    if not is_gcs_uri(perm_output):
        return perm_output

    local_out_root = os.path.join(scratch_root, "group_inputs")
    rel_preproc = os.path.join(sub_id, f"ses-{ses_id}", "func_preproc", f"{sub_id}_preproc.results")
    rel_glm = os.path.join(sub_id, f"ses-{ses_id}", "glm", analysis_name, f"{sub_id}_{analysis_name}.results")

    local_preproc_dir = os.path.join(local_out_root, rel_preproc)
    local_glm_dir = os.path.join(local_out_root, rel_glm)

    mask_head = os.path.join(local_preproc_dir, f"mask_epi_anat.{sub_id}_preproc+tlrc.HEAD")
    if not os.path.exists(mask_head):
        gcs_mask_pattern = join_uri(
            perm_output, rel_preproc.replace(os.sep, "/"), f"mask_epi_anat.{sub_id}_preproc+tlrc.*"
        )
        gcs_download_wildcard(gcs_mask_pattern, local_preproc_dir)

    stats_head = os.path.join(local_glm_dir, f"stats.{sub_id}_{analysis_name}+tlrc.HEAD")
    if not os.path.exists(stats_head):
        gcs_stats_pattern = join_uri(
            perm_output, rel_glm.replace(os.sep, "/"), f"stats.{sub_id}_{analysis_name}+tlrc.*"
        )
        gcs_download_wildcard(gcs_stats_pattern, local_glm_dir)

    return local_out_root


def run_group_analysis(
    args: argparse.Namespace,
    config: Dict[str, Any],
    analysis_models: Dict[str, Any],
) -> bool:
    """Runs a specified group-level analysis with optional scratch and GCS acceleration."""
    console.print(Panel(f"Group Analysis: [bold cyan]{args.group_model}[/]", style="bold blue"))

    if not args.analysis or len(args.analysis) > 1:
        console.log("[red]Error:[/] Please specify exactly one first-level analysis model using --analysis.")
        return False
    analysis_name = args.analysis[0]

    if not args.group_model:
        console.log("[red]Error:[/] Please specify a group analysis model using --group_model.")
        return False

    f_level_model = analysis_models.get(analysis_name)
    if not f_level_model:
        console.log(f"[red]Error:[/] First-level analysis '{analysis_name}' not found.")
        return False

    group_model_config = next(
        (g for g in f_level_model.get("group_analyses", []) if g["name"] == args.group_model),
        None,
    )
    if not group_model_config:
        console.log(f"[red]Error:[/] Group analysis model '{args.group_model}' not found under '{analysis_name}'.")
        return False

    use_scratch = not getattr(args, "no_scratch", False)
    scratch_root = getattr(args, "scratch_dir", None) or config.get("scratch_dir", "/tmp/afni_scratch")

    perm_output_dir = join_uri(config["output_dir"], "group_analysis", analysis_name, args.group_model)
    if is_gcs_uri(config["output_dir"]) or (use_scratch and scratch_root):
        active_output_dir = os.path.join(scratch_root, "group_analysis", analysis_name, args.group_model)
    else:
        active_output_dir = perm_output_dir

    os.makedirs(active_output_dir, exist_ok=True)
    if not is_gcs_uri(perm_output_dir):
        os.makedirs(perm_output_dir, exist_ok=True)

    try:
        all_subjects_info = config.get("subjects", [])
        subjects_to_process = []

        if "subjects" in group_model_config:
            custom_subjects = group_model_config["subjects"]
            subjects_ids_to_include: List[str] = []

            if isinstance(custom_subjects, list):
                subjects_ids_to_include = custom_subjects
                console.log(f"Using custom list of {len(subjects_ids_to_include)} subjects.")
            elif isinstance(custom_subjects, dict):
                console.log("Using custom subject lists per group.")
                valid_groups = group_model_config.get("groups", [])
                for group_name, subject_list in custom_subjects.items():
                    if group_name not in valid_groups:
                        continue
                    subjects_ids_to_include.extend(subject_list)

            subject_id_map = {s["id"]: s for s in all_subjects_info}
            for sub_id in subjects_ids_to_include:
                if sub_id in subject_id_map:
                    subjects_to_process.append(subject_id_map[sub_id])
                else:
                    console.log(f"[yellow]Warning:[/] Subject '{sub_id}' from custom list not found.")
        else:
            group_model_groups = group_model_config.get("groups")
            if group_model_groups:
                console.log(f"Using all subjects from group(s): {group_model_groups}")
                subjects_to_process = [s for s in all_subjects_info if s.get("group") in group_model_groups]
            else:
                subjects_to_process = all_subjects_info

        if not subjects_to_process:
            console.log("[red]Error:[/] No subjects to process after filtering.")
            return False

        mask_files: List[str] = []
        for sub_info in subjects_to_process:
            for ses_id in group_model_config.get("sessions", []):
                local_data_root = _stage_group_subject_files(
                    config, scratch_root, sub_info["id"], ses_id, analysis_name
                )
                mask_path = os.path.join(
                    local_data_root,
                    sub_info["id"],
                    f"ses-{ses_id}",
                    "func_preproc",
                    f"{sub_info['id']}_preproc.results",
                    f"mask_epi_anat.{sub_info['id']}_preproc+tlrc.HEAD",
                )
                if os.path.exists(mask_path):
                    mask_files.append(mask_path.replace(".HEAD", ""))
                else:
                    console.log(f"[yellow]Warning:[/] Mask file not found: {mask_path}")

        if not mask_files:
            console.log("[red]Error:[/] No mask files found.")
            return False

        group_mask_path = os.path.join(active_output_dir, "group_mask")
        subprocess.run(
            ["3dmask_tool", "-input"] + mask_files + ["-prefix", group_mask_path, "-frac", "0.4", "-overwrite"],
            check=True,
        )

        analysis_type = group_model_config["type"]
        base_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(base_dir, "scripts", "04_run_group_analysis.sh")

        command = [
            "bash",
            script_path,
            "--type",
            analysis_type,
            "--output_prefix",
            os.path.join(active_output_dir, f"result_{args.group_model}"),
            "--mask",
            f"{group_mask_path}+tlrc",
        ]

        if analysis_type == "3dLMEr":
            table_columns = group_model_config.get("table_columns", [])
            if not table_columns:
                console.log("[red]Error:[/] 'table_columns' is missing in config.")
                return False
            header_columns = ["Subj"] + table_columns + ["InputFile"]
            header = "\t".join(header_columns) + "\n"

            data_table_path = os.path.join(active_output_dir, "data_table.txt")
            if "data_table_rows" not in group_model_config:
                console.log("[red]Error:[/] 'data_table_rows' is missing in config.")
                return False

            with open(data_table_path, "w") as f:
                f.write(header)
                for sub_info in subjects_to_process:
                    for ses_id in group_model_config.get("sessions", []):
                        local_data_root = _stage_group_subject_files(
                            config, scratch_root, sub_info["id"], ses_id, analysis_name
                        )
                        for row_def in group_model_config["data_table_rows"]:
                            contrast_name = row_def["contrast"]
                            stats_file = os.path.join(
                                local_data_root,
                                sub_info["id"],
                                f"ses-{ses_id}",
                                "glm",
                                analysis_name,
                                f"{sub_info['id']}_{analysis_name}.results",
                                f"stats.{sub_info['id']}_{analysis_name}+tlrc[{contrast_name}]",
                            )
                            if not os.path.exists(stats_file.split("[")[0] + ".HEAD"):
                                console.log(f"[yellow]Warning:[/] Stats file not found: {stats_file}")
                                continue

                            row_data = {
                                "Subj": sub_info["id"],
                                "session": f"ses-{ses_id}",
                                "group": sub_info.get("group", "NA"),
                                "InputFile": stats_file,
                            }
                            for key, value in row_def.items():
                                if key != "contrast":
                                    row_data[key] = value

                            line_parts = [str(row_data.get(col_name, "NA")) for col_name in header_columns]
                            f.write("\t".join(line_parts) + "\n")

            glt_codes = " ".join([f"-gltCode {g['label']} \"{g['sym']}\"" for g in group_model_config.get("glt", [])])
            command.extend([
                "--data_table",
                data_table_path,
                "--model",
                group_model_config["model"],
                "--glt_codes",
                glt_codes,
            ])

        elif analysis_type == "3dttest++":
            setA_label = group_model_config.get("setA_label")
            contrast_name = group_model_config.get("contrast")
            if not setA_label or not contrast_name:
                console.log("[red]Error:[/] 3dttest++ requires 'setA_label' and 'contrast'.")
                return False

            setA_files: List[str] = []
            for sub_info in subjects_to_process:
                for ses_id in group_model_config.get("sessions", []):
                    local_data_root = _stage_group_subject_files(
                        config, scratch_root, sub_info["id"], ses_id, analysis_name
                    )
                    stats_file = os.path.join(
                        local_data_root,
                        sub_info["id"],
                        f"ses-{ses_id}",
                        "glm",
                        analysis_name,
                        f"{sub_info['id']}_{analysis_name}.results",
                        f"stats.{sub_info['id']}_{analysis_name}+tlrc[{contrast_name}]",
                    )
                    if not os.path.exists(stats_file.split("[")[0] + ".HEAD"):
                        console.log(f"[yellow]Warning:[/] Stats file not found: {stats_file}")
                        continue
                    setA_files.append(sub_info["id"])
                    setA_files.append(f"{stats_file}")

            command.extend(["--setA_label", setA_label, "--setA_files", " ".join(setA_files)])

        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_filename = f"group_analysis_{analysis_name}_{args.group_model}.log"
        log_file_path = os.path.join(log_dir, log_filename)
        console.log(f"[dim]Executing group analysis. See log: {log_file_path}[/]")

        try:
            with open(log_file_path, "w") as log_file:
                process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, cwd=active_output_dir)
                process.wait()
        finally:
            if is_gcs_uri(config["output_dir"]) and os.path.exists(log_file_path):
                gcs_upload_file(log_file_path, join_uri(config["output_dir"], "logs", log_filename))

        if process.returncode == 0:
            console.log(f"[bold green]SUCCESS:[/] Group analysis complete in: {active_output_dir}")
            if is_gcs_uri(perm_output_dir):
                console.log(f"[cyan]Uploading group analysis results to GCS ({perm_output_dir})...[/]")
                gcs_sync_up(active_output_dir, perm_output_dir)
                console.log(f"[bold green]SUCCESS:[/] Results preserved in: {perm_output_dir}")
            elif active_output_dir != perm_output_dir:
                console.log("[cyan]Syncing group analysis results to permanent output drive...[/]")
                subprocess.run(["rsync", "-av", "--update", f"{active_output_dir}/", f"{perm_output_dir}/"], check=True)
                console.log(f"[bold green]SUCCESS:[/] Results preserved in: {perm_output_dir}")
            return True

        console.log(f"[bold red]ERROR:[/] Group analysis failed. Check log: {log_file_path}")
        return False

    finally:
        if (active_output_dir != perm_output_dir or is_gcs_uri(perm_output_dir)) and config.get("cleanup_scratch", True):
            console.log("[dim]Cleaning local group analysis scratch...[/]")
            shutil.rmtree(active_output_dir, ignore_errors=True)
            shutil.rmtree(os.path.join(scratch_root, "group_inputs"), ignore_errors=True)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments for WAR analysis pipeline."""
    parser = argparse.ArgumentParser(description="fMRI Analysis Pipeline Runner for WAR task")
    parser.add_argument(
        "--subject",
        nargs="*",
        default=["all"],
        help="Specify subject IDs to process (e.g., sub-MD01) or 'all'.",
    )
    parser.add_argument(
        "--analysis",
        nargs="*",
        default=["all"],
        help="Specify one or more analysis models to run for 'glm', 'all', or 'group_analysis' step.",
    )
    parser.add_argument(
        "--step",
        nargs="+",
        default=["all"],
        help="One or more processing steps to execute in sequence (e.g., --step preprocess glm).",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=None,
        help="Specify the session number (e.g., 1). If omitted, all sessions will be processed.",
    )
    parser.add_argument("--n_procs", type=int, default=1, help="Number of subjects to process in parallel.")
    parser.add_argument("--group_model", default="all", help="Specify the group analysis model name to run.")
    parser.add_argument("--scratch_dir", default=None, help="Override scratch directory path.")
    parser.add_argument("--clean_scratch", action="store_true", help="Clean scratch upon finish.")
    parser.add_argument("--no_scratch", action="store_true", help="Disable local scratch directory.")
    parser.add_argument("--input_dir", default=None, help="Override input_dir from main_config.toml.")
    parser.add_argument("--output_dir", default=None, help="Override output_dir from main_config.toml.")
    parser.add_argument("--reports_dir", default=None, help="Override reports_dir / destination for exported QC PDFs.")
    parser.add_argument("--keep_pb00_pb04", action="store_true", help="Keep intermediate pb00-pb04 bricks.")
    parser.add_argument("--export_qc", action="store_true", help="Export consolidated QC PDF reports after processing.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point to run the WAR analysis pipeline."""
    args = parse_args(argv)
    step_display = ", ".join(args.step) if isinstance(args.step, list) else str(args.step)
    console.print(Panel(f"fMRI Analysis Pipeline (WAR)\n[dim]Step(s): {step_display}[/]", style="bold blue"))

    base_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        main_config_path = os.path.join(base_dir, "analysis_configs", "main_config.toml")
        models_config_path = os.path.join(base_dir, "analysis_configs", "analysis_models.toml")
        main_config = json.loads(json.dumps(toml.load(main_config_path) if hasattr(toml, "load") else toml.loads(open(main_config_path).read())))
        analysis_models = json.loads(json.dumps(toml.load(models_config_path) if hasattr(toml, "load") else toml.loads(open(models_config_path).read())))
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/] Configuration file not found. {exc}")
        return 1

    # Allow CLI or environment variable overrides for cloud execution
    if args.input_dir or os.environ.get("MRI_INPUT_DIR"):
        main_config["input_dir"] = args.input_dir or os.environ["MRI_INPUT_DIR"]
    if args.output_dir or os.environ.get("MRI_OUTPUT_DIR"):
        main_config["output_dir"] = args.output_dir or os.environ["MRI_OUTPUT_DIR"]
    if args.reports_dir or os.environ.get("MRI_REPORTS_DIR"):
        main_config["reports_dir"] = args.reports_dir or os.environ["MRI_REPORTS_DIR"]
    if args.keep_pb00_pb04 or os.environ.get("KEEP_PB00_PB04") == "1":
        main_config["keep_pb00_pb04"] = True
    if args.clean_scratch:
        main_config["cleanup_scratch"] = True

    if "group_analysis" in args.step:
        success = run_group_analysis(args, main_config, analysis_models)
        return 0 if success else 1

    expanded_steps = expand_steps(args.step)

    subjects_to_process_ids: List[str] = []
    if args.subject and args.subject != ["all"] and args.subject != "all":
        subjects_to_process_ids = [subj for subj in args.subject] if isinstance(args.subject, list) else [args.subject]
    elif args.analysis and args.analysis != ["all"] and "glm" in expanded_steps:
        first_analysis = args.analysis[0]
        model = analysis_models.get(first_analysis, {})
        if "subjects" in model:
            subjects_to_process_ids = model["subjects"]
        elif "subjects" in main_config:
            subjects_to_process_ids = [s["id"] for s in main_config.get("subjects", [])]
        else:
            subjects_to_process_ids = []
    elif "subjects" in main_config:
        subjects_to_process_ids = [s["id"] for s in main_config.get("subjects", [])]
    else:
        subjects_to_process_ids = []

    # Automatically shard subjects if running inside a Cloud Batch / Cloud Run Job array
    subjects_to_process_ids = shard_subjects_for_cloud_task(subjects_to_process_ids, console=console)

    if not subjects_to_process_ids:
        console.print("[yellow]No subjects found to process for this task. Exiting cleanly.[/]")
        return 0

    if args.analysis and args.analysis != ["all"]:
        for analysis_name in args.analysis:
            if analysis_name not in analysis_models:
                console.print(f"[bold red]Error:[/] Analysis model '{analysis_name}' not found.")
                return 1

    console.print(f"Processing [bold cyan]{len(subjects_to_process_ids)}[/] subject(s): {subjects_to_process_ids}")

    failed_subjects: List[str] = []
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
            console.log(f"[yellow]Parallel processing with {args.n_procs} cores enabled.[/]")
            worker_func = partial(
                process_subject,
                args=args,
                main_config=main_config,
                analysis_models=analysis_models,
                progress=None,
                task_id=None,
            )
            with ProcessPoolExecutor(max_workers=args.n_procs) as executor:
                futures = {executor.submit(worker_func, sub_id): sub_id for sub_id in subjects_to_process_ids}
                for future in futures:
                    sub_id = futures[future]
                    try:
                        ok = future.result()
                        if not ok:
                            failed_subjects.append(sub_id)
                    except Exception as exc:
                        console.log(f"[bold red]Exception occurred processing {sub_id}:[/] {exc}")
                        failed_subjects.append(sub_id)
                    progress.update(main_task, advance=1)
        else:
            for subject_id in subjects_to_process_ids:
                ok = process_subject(subject_id, args, main_config, analysis_models, progress, main_task)
                if not ok:
                    failed_subjects.append(subject_id)
                progress.update(main_task, advance=1)

    # Automatically export QC PDFs if enabled and step produces visual QC artifacts
    export_qc_enabled = (
        args.export_qc
        or os.environ.get("EXPORT_QC_PDFS", "").lower() in ("true", "1", "yes")
    )
    dest_reports_dir = main_config.get("reports_dir")

    qc_steps = {"preprocess_anat", "preprocess_func", "glm", "preprocess", "all"}
    has_qc_steps = any(s in qc_steps for s in expanded_steps)

    if export_qc_enabled and dest_reports_dir:
        if has_qc_steps:
            successful_subjects = [s for s in subjects_to_process_ids if s not in failed_subjects]
            if successful_subjects and export_subject_results is not None:
                console.print(
                    Panel(
                        f"Exporting QC PDF reports for [bold cyan]{len(successful_subjects)}[/] subject(s)\n"
                        f"[dim]Destination: {dest_reports_dir}[/]",
                        style="bold cyan",
                    )
                )
                tmp_work_dir = (
                    tempfile.mkdtemp(prefix="afni_export_")
                    if (is_gcs_uri(main_config["output_dir"]) or is_gcs_uri(dest_reports_dir))
                    else None
                )
                try:
                    for sub_id in successful_subjects:
                        sub_conf = next((s for s in main_config.get("subjects", []) if s.get("id") == sub_id), None)
                        if not sub_conf:
                            sub_conf = {"id": sub_id, "group": "WAR", "sessions": [{"id": 1}]}
                        try:
                            export_subject_results(
                                subject_config=sub_conf,
                                output_dir=main_config["output_dir"],
                                dest_root=dest_reports_dir,
                                analysis_models=analysis_models,
                                tmp_work_dir=tmp_work_dir,
                            )
                        except Exception as exc:
                            console.log(f"[yellow]Warning:[/] Failed to export QC PDFs for {sub_id}: {exc}")
                finally:
                    if tmp_work_dir and os.path.exists(tmp_work_dir):
                        shutil.rmtree(tmp_work_dir, ignore_errors=True)
        else:
            console.log(f"[dim]Skipping QC PDF export: requested step(s) {expanded_steps} produce no visual QC artifacts.[/]")

    if failed_subjects:
        console.print(
            Panel(
                f"[bold red]Pipeline failed for {len(failed_subjects)} subject(s): {', '.join(failed_subjects)}[/]",
                style="bold red",
            )
        )
        return 1

    console.print(Panel("[bold green]All processing complete successfully[/]", style="green"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
