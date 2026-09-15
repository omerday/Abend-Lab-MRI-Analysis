import os
import glob
import re
import asyncio
import time
import datetime
from typing import List, Dict, Any, Optional, Callable
from .config import config, load_toml

class BatchJobTracker:
    def __init__(self, job_id: str, pipeline: str, step: str, subjects: List[str], 
                 analysis: Optional[List[str]] = None, session: Optional[str] = None, 
                 n_procs: int = 1, group_model: Optional[str] = None):
        self.job_id = job_id
        self.pipeline = pipeline
        self.step = step
        self.subjects = list(subjects)
        self.analysis = analysis or []
        self.session = session or "1"
        self.n_procs = n_procs
        self.group_model = group_model
        
        self.process: Optional[asyncio.subprocess.Process] = None
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.exit_code: Optional[int] = None
        self.command_list: List[str] = []
        
        # State per subject: { subject_id: { 'status': 'QUEUED'|'RUNNING'|'SUCCESS'|'FAILED', ... } }
        self.subject_states: Dict[str, Dict[str, Any]] = {
            s: {
                "status": "QUEUED",
                "current_step": "Waiting to start",
                "active_analysis": None,
                "chauffeur_images": [],
                "qc_pdfs": [],
                "error_snippet": None,
                "notified": False,
                "start_time": None,
                "finish_time": None,
            }
            for s in self.subjects
        }

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    @property
    def elapsed_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def formatted_elapsed(self) -> str:
        s = int(self.elapsed_seconds)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        elif m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.subject_states.values() if s["status"] in ["SUCCESS", "FAILED"])

    @property
    def success_count(self) -> int:
        return sum(1 for s in self.subject_states.values() if s["status"] == "SUCCESS")

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.subject_states.values() if s["status"] == "FAILED")

    @property
    def progress_percent(self) -> int:
        total = len(self.subjects)
        if total == 0:
            return 100
        return int((self.completed_count / total) * 100)


class PipelineManager:
    def __init__(self):
        self.active_batch: Optional[BatchJobTracker] = None
        self.history: List[BatchJobTracker] = []
        self._monitor_task: Optional[asyncio.Task] = None

    def get_pipeline_info(self, pipeline: str) -> Dict[str, Any]:
        """Read main_config.toml and analysis_models.toml dynamically for a pipeline."""
        p_dir = config.get_pipeline_dir(pipeline)
        main_cfg_path = os.path.join(p_dir, "analysis_configs", "main_config.toml")
        model_cfg_path = os.path.join(p_dir, "analysis_configs", "analysis_models.toml")

        main_cfg = {}
        model_cfg = {}
        if os.path.exists(main_cfg_path) and load_toml is not None:
            main_cfg = load_toml(main_cfg_path)
        if os.path.exists(model_cfg_path) and load_toml is not None:
            model_cfg = load_toml(model_cfg_path)

        # Extract subjects
        subjects = []
        if "subjects" in main_cfg and isinstance(main_cfg["subjects"], list):
            subjects = [s["id"] for s in main_cfg["subjects"] if isinstance(s, dict) and "id" in s]
        elif "all_subjects" in main_cfg:
            subjects = list(main_cfg["all_subjects"])

        # Extract models & group analyses
        models = list(model_cfg.keys())
        group_models = []
        for m_name, m_val in model_cfg.items():
            if isinstance(m_val, dict) and "group_analyses" in m_val:
                for ga in m_val["group_analyses"]:
                    if isinstance(ga, dict) and "name" in ga:
                        group_models.append(ga["name"])

        return {
            "pipeline": pipeline,
            "directory": p_dir,
            "input_dir": main_cfg.get("input_dir", ""),
            "output_dir": main_cfg.get("output_dir", ""),
            "subjects": subjects,
            "models": models,
            "group_models": group_models,
        }

    def get_subject_available_models(self, pipeline: str, subject: str) -> List[Dict[str, Any]]:
        """Identify which analysis models have generated results/images for this subject."""
        info = self.get_pipeline_info(pipeline)
        known_models = list(info["models"])
        
        # Discover all artifacts for this subject
        all_artifacts = self.find_qa_artifacts(pipeline, subject, analysis=None)
        all_imgs = all_artifacts["chauffeur_images"]
        all_pdfs = all_artifacts["qc_pdfs"]

        models_summary = []

        # Check preprocessing artifacts
        preproc_imgs = [img for img in all_imgs if "anat_warped" in img or "preproc" in img]
        preproc_pdfs = [pdf for pdf in all_pdfs if "preproc" in pdf or "anat" in pdf]
        models_summary.append({
            "id": "preproc",
            "label": "Preprocessing (Anat & Func)",
            "image_count": len(preproc_imgs),
            "pdf_count": len(preproc_pdfs),
            "has_data": bool(preproc_imgs or preproc_pdfs),
        })

        # Check each known GLM model
        for model in known_models:
            m_imgs = [img for img in all_imgs if f"/{model}/" in img or f"_{model}/" in img or f"_{model}." in img or f"/{model}." in img]
            m_pdfs = [pdf for pdf in all_pdfs if f"_{model}_" in pdf or f"_{model}." in pdf or f"/{model}/" in pdf]
            models_summary.append({
                "id": model,
                "label": model,
                "image_count": len(m_imgs),
                "pdf_count": len(m_pdfs),
                "has_data": bool(m_imgs or m_pdfs),
            })

        # Sort so models with data appear first
        models_summary.sort(key=lambda x: (not x["has_data"], x["id"] != "preproc", x["id"]))
        return models_summary

    def get_available_group_models(self, pipeline: str) -> List[Dict[str, Any]]:
        """Identify configured and executed group analysis models for this pipeline."""
        info = self.get_pipeline_info(pipeline)
        configured_group_models = list(info.get("group_models", []))
        
        # For TIM, group analyses are defined under models
        if not configured_group_models and pipeline.lower() == "tim":
            p_dir = info["directory"]
            model_cfg_path = os.path.join(p_dir, "analysis_configs", "analysis_models.toml")
            if os.path.exists(model_cfg_path) and load_toml is not None:
                m_cfg = load_toml(model_cfg_path)
                for m_name, m_val in m_cfg.items():
                    if isinstance(m_val, dict) and "group_analysis" in m_val:
                        configured_group_models.append(m_name)

        # Also scan the filesystem for existing group analysis folders
        output_dir = info["output_dir"]
        discovered_models = set(configured_group_models)
        if output_dir and os.path.isdir(os.path.join(output_dir, "group_analysis")):
            base_ga = os.path.join(output_dir, "group_analysis")
            for root, dirs, files in os.walk(base_ga):
                for d in dirs:
                    if d.startswith("sub-"): continue
                    if d != "chauffeur_images" and not d.endswith("_images"):
                        discovered_models.add(d)

        group_list = []
        for gm in sorted(discovered_models):
            qa = self.find_group_qa_artifacts(pipeline, gm)
            group_list.append({
                "id": gm,
                "label": gm,
                "image_count": len(qa["chauffeur_images"]),
                "pdf_count": len(qa["qc_pdfs"]),
                "has_data": bool(qa["chauffeur_images"] or qa["qc_pdfs"]),
            })

        group_list.sort(key=lambda x: (not x["has_data"], x["id"]))
        return group_list

    def find_qa_artifacts(self, pipeline: str, subject: str, analysis: Optional[str] = None) -> Dict[str, Any]:
        """Search derivatives and Dropbox directories for generated chauffeur PNGs and QC PDFs for a subject."""
        info = self.get_pipeline_info(pipeline)
        output_dir = info["output_dir"]
        p_dir = info["directory"]
        known_models = list(info["models"])

        candidate_dirs = [output_dir, p_dir, os.path.expanduser("~/Dropbox")]
        chauffeur_images = []
        qc_pdfs = []

        for base in candidate_dirs:
            if not base or not os.path.isdir(base):
                continue
            
            # 1. Search for chauffeur PNGs
            sub_patterns = [
                os.path.join(base, f"{subject}*", "**", "chauffeur_images", "*.png"),
                os.path.join(base, f"{subject}*", "**", "QC", "*.png"),
                os.path.join(base, f"{subject}*", "**", "chauffeur", "*.png"),
                os.path.join(base, f"{subject}*", "**", "anat_warped", "*.png"),
            ]
            for pat in sub_patterns:
                for img in glob.glob(pat, recursive=True):
                    # Filter by analysis if requested
                    if analysis:
                        if analysis == "preproc":
                            if "anat_warped" not in img and "preproc" not in img:
                                continue
                        else:
                            if f"/{analysis}/" not in img and f"_{analysis}/" not in img and f"_{analysis}." not in img:
                                continue

                    if img not in chauffeur_images:
                        chauffeur_images.append(img)

            # 2. Search for QC PDFs
            pdf_patterns = [
                os.path.join(base, f"{subject}*", "**", "*.pdf"),
                os.path.join(base, f"*{subject}*.pdf"),
                os.path.join(base, f"{subject}*.pdf"),
            ]
            for pat in pdf_patterns:
                for pdf in glob.glob(pat, recursive=True):
                    if analysis:
                        if analysis == "preproc":
                            if "preproc" not in pdf and "anat" not in pdf:
                                continue
                        else:
                            if f"_{analysis}_" not in pdf and f"_{analysis}." not in pdf and f"/{analysis}/" not in pdf:
                                continue

                    if pdf not in qc_pdfs:
                        qc_pdfs.append(pdf)

        chauffeur_images.sort(key=os.path.getmtime, reverse=True)
        qc_pdfs.sort(key=os.path.getmtime, reverse=True)

        # Build annotated image list
        annotated_images = []
        for img in chauffeur_images:
            fname = os.path.basename(img)
            stim = fname.replace(".png", "")
            
            # Detect model from path
            detected_model = "Unknown"
            if "anat_warped" in img or "preproc" in img:
                detected_model = "Preprocessing"
            else:
                for m in known_models:
                    if f"/{m}/" in img or f"_{m}/" in img or f"_{m}." in img:
                        detected_model = m
                        break

            annotated_images.append({
                "path": img,
                "filename": fname,
                "stimulus": stim,
                "model": detected_model,
            })

        return {
            "chauffeur_images": chauffeur_images,
            "annotated_images": annotated_images,
            "qc_pdfs": qc_pdfs,
        }

    def find_group_qa_artifacts(self, pipeline: str, group_model: Optional[str] = None) -> Dict[str, Any]:
        """Search derivatives and Dropbox directories for generated group-level chauffeur PNGs and PDFs."""
        info = self.get_pipeline_info(pipeline)
        output_dir = info["output_dir"]
        p_dir = info["directory"]

        candidate_dirs = [output_dir, p_dir, os.path.expanduser("~/Dropbox")]
        chauffeur_images = []
        qc_pdfs = []

        for base in candidate_dirs:
            if not base or not os.path.isdir(base):
                continue

            patterns = [
                os.path.join(base, "group_analysis", "**", "*.png"),
                os.path.join(base, "**", "group_*", "**", "*.png"),
                os.path.join(base, "**", "*_images", "*.png"),
            ]
            for pat in patterns:
                for img in glob.glob(pat, recursive=True):
                    if group_model and group_model not in img:
                        continue
                    if img not in chauffeur_images:
                        chauffeur_images.append(img)

            pdf_patterns = [
                os.path.join(base, "group_analysis", "**", "*.pdf"),
                os.path.join(base, "**", "group_*", "**", "*.pdf"),
            ]
            for pat in pdf_patterns:
                for pdf in glob.glob(pat, recursive=True):
                    if group_model and group_model not in pdf:
                        continue
                    if pdf not in qc_pdfs:
                        qc_pdfs.append(pdf)

        chauffeur_images.sort(key=os.path.getmtime, reverse=True)
        qc_pdfs.sort(key=os.path.getmtime, reverse=True)

        annotated_images = []
        for img in chauffeur_images:
            fname = os.path.basename(img)
            annotated_images.append({
                "path": img,
                "filename": fname,
                "stimulus": fname.replace(".png", ""),
                "group_model": group_model or "Group",
            })

        return {
            "chauffeur_images": chauffeur_images,
            "annotated_images": annotated_images,
            "qc_pdfs": qc_pdfs,
        }

    def get_log_tail(self, pipeline: str, subject: str, step: Optional[str] = None, 
                     analysis: Optional[str] = None, lines_count: int = 35) -> str:
        """Fetch the tail of the most relevant log file for a subject."""
        p_dir = config.get_pipeline_dir(pipeline)
        log_dir = os.path.join(p_dir, "logs")
        if not os.path.isdir(log_dir):
            return "No logs directory found."

        candidates = glob.glob(os.path.join(log_dir, f"{subject}*.log"))
        if not candidates:
            return f"No log files found for subject {subject} in {log_dir}."

        # Filter by analysis or step if provided
        if analysis:
            filtered = [c for c in candidates if analysis in os.path.basename(c)]
            if filtered: candidates = filtered
        if step:
            filtered = [c for c in candidates if step in os.path.basename(c)]
            if filtered: candidates = filtered

        # Pick the most recently modified matching log file
        target_log = max(candidates, key=os.path.getmtime)
        
        try:
            with open(target_log, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                tail = "".join(lines[-lines_count:]) if lines else "Log file is currently empty."
                header = f"📄 {os.path.basename(target_log)} (Last {min(lines_count, len(lines))} lines):\n"
                return header + tail
        except Exception as e:
            return f"Error reading log file {target_log}: {e}"

    async def launch_batch(
        self,
        pipeline: str,
        step: str,
        subjects: Optional[List[str]] = None,
        analysis: Optional[List[str]] = None,
        session: Optional[str] = "1",
        n_procs: int = 1,
        group_model: Optional[str] = None,
        on_subject_milestone: Optional[Callable[[BatchJobTracker, str, Dict[str, Any]], Any]] = None,
        on_batch_complete: Optional[Callable[[BatchJobTracker], Any]] = None,
    ) -> BatchJobTracker:
        """Launch a run_analysis.py batch run across single or multiple subjects."""
        if self.active_batch and self.active_batch.is_running:
            raise RuntimeError(f"Another batch is already active (PID: {self.active_batch.process.pid if self.active_batch.process else '?'}). Wait for it to finish or /kill it.")

        p_info = self.get_pipeline_info(pipeline)
        p_dir = p_info["directory"]

        # Resolve subjects to process
        resolved_subjects = subjects
        if not resolved_subjects:
            resolved_subjects = p_info["subjects"]
        if not resolved_subjects:
            raise ValueError(f"No subjects found for pipeline '{pipeline}'. Specify --subjects explicitly.")

        job_id = f"batch_{pipeline}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        tracker = BatchJobTracker(
            job_id=job_id,
            pipeline=pipeline,
            step=step,
            subjects=resolved_subjects,
            analysis=analysis,
            session=session,
            n_procs=n_procs,
            group_model=group_model,
        )

        # Build command line
        cmd = ["python3", "run_analysis.py", "--step", step]
        if resolved_subjects:
            cmd.extend(["--subject"] + resolved_subjects)
        if analysis:
            cmd.extend(["--analysis"] + analysis)
        if session:
            cmd.extend(["--session", str(session)])
        if n_procs > 1:
            cmd.extend(["--n_procs", str(n_procs)])
        if group_model:
            cmd.extend(["--group_model", group_model])

        tracker.command_list = cmd

        # Start process
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=p_dir,
            stdout=asyncio.subprocess.DEVNULL, # Logs are written directly to logs/ by run_analysis.py
            stderr=asyncio.subprocess.DEVNULL,
        )
        tracker.process = process
        self.active_batch = tracker

        # Launch background monitor task
        self._monitor_task = asyncio.create_task(
            self._monitor_batch_loop(tracker, on_subject_milestone, on_batch_complete)
        )

        return tracker

    async def _monitor_batch_loop(
        self,
        tracker: BatchJobTracker,
        on_subject_milestone: Optional[Callable[[BatchJobTracker, str, Dict[str, Any]], Any]],
        on_batch_complete: Optional[Callable[[BatchJobTracker], Any]],
    ):
        """Asynchronous monitor loop checking individual subject logs and outputs."""
        p_dir = config.get_pipeline_dir(tracker.pipeline)
        log_dir = os.path.join(p_dir, "logs")

        poll_interval = config.poll_interval_seconds

        while tracker.is_running:
            await asyncio.sleep(poll_interval)
            await self._check_subject_progress(tracker, log_dir, on_subject_milestone)

        # Process has terminated
        tracker.end_time = time.time()
        tracker.exit_code = tracker.process.returncode

        # Final sweep to catch all completed/failed states
        await self._check_subject_progress(tracker, log_dir, on_subject_milestone, final_sweep=True)

        if on_batch_complete:
            try:
                res = on_batch_complete(tracker)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"[Error in on_batch_complete callback]: {e}")

        self.history.append(tracker)
        if self.active_batch == tracker:
            self.active_batch = None

    async def _check_subject_progress(
        self,
        tracker: BatchJobTracker,
        log_dir: str,
        on_subject_milestone: Optional[Callable[[BatchJobTracker, str, Dict[str, Any]], Any]],
        final_sweep: bool = False,
    ):
        """Inspect per-subject logs and output directories to update subject states."""
        for subject_id, state in tracker.subject_states.items():
            if state["status"] in ["SUCCESS", "FAILED"] and state["notified"]:
                continue # Already completed and notified

            # Find all logs for this subject modified during this batch
            subject_logs = glob.glob(os.path.join(log_dir, f"{subject_id}*.log"))
            recent_logs = [l for l in subject_logs if os.path.getmtime(l) >= tracker.start_time - 30]

            if not recent_logs and not final_sweep:
                # Still in queue or starting
                continue

            # Determine latest active log
            if recent_logs:
                latest_log = max(recent_logs, key=os.path.getmtime)
                fname = os.path.basename(latest_log)
                
                # Check log content
                last_lines = []
                try:
                    with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
                        last_lines = [line.strip() for line in f if line.strip()]
                except Exception:
                    pass
                
                combined_tail = " ".join(last_lines[-10:]).lower() if last_lines else ""

                # Check if currently running or finished
                if any(w in combined_tail for w in ["error", "failed", "cannot", "abort", "fatal"]):
                    state["status"] = "FAILED"
                    state["error_snippet"] = "\n".join(last_lines[-15:])
                    state["finish_time"] = time.time()
                elif any(w in combined_tail for w in ["successfully completed", "complete", "success", "script finished"]):
                    # If step is 'all' or multiple analyses, verify if this was the final step (GLM)
                    is_final_step = (tracker.step == "glm" or "glm" in fname or tracker.step != "all")
                    if is_final_step or final_sweep:
                        state["status"] = "SUCCESS"
                        state["finish_time"] = time.time()
                    else:
                        state["status"] = "RUNNING"
                        state["current_step"] = fname.replace(f"{subject_id}_", "").replace(".log", "")
                else:
                    state["status"] = "RUNNING"
                    state["current_step"] = fname.replace(f"{subject_id}_", "").replace(".log", "")
            
            elif final_sweep and state["status"] not in ["SUCCESS", "FAILED"]:
                # If batch completed but subject didn't succeed, check exit code
                if tracker.exit_code == 0:
                    state["status"] = "SUCCESS"
                else:
                    state["status"] = "FAILED"
                    state["error_snippet"] = "Batch process exited before subject completed."

            # If subject transitioned to terminal state (SUCCESS or FAILED) and hasn't notified yet
            if state["status"] in ["SUCCESS", "FAILED"] and not state["notified"]:
                # Find artifacts
                qa_data = self.find_qa_artifacts(tracker.pipeline, subject_id)
                state["chauffeur_images"] = qa_data["chauffeur_images"]
                state["qc_pdfs"] = qa_data["qc_pdfs"]

                state["notified"] = True
                if on_subject_milestone:
                    try:
                        res = on_subject_milestone(tracker, subject_id, state)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        print(f"[Error in on_subject_milestone for {subject_id}]: {e}")

    async def run_export_for_subject(self, pipeline: str, subject: str) -> Dict[str, Any]:
        """Run export_results.py for a specific subject, generating QA PDFs into ~/Dropbox.
        
        Returns a dict with 'success' (bool), 'pdf_count' (int), and 'output' (str).
        """
        p_dir = config.get_pipeline_dir(pipeline)
        export_script = os.path.join(p_dir, "export_results.py")

        if not os.path.exists(export_script):
            return {"success": False, "pdf_count": 0, "output": f"export_results.py not found in {p_dir}"}

        cmd = ["python3", "export_results.py", "--subject", subject]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=p_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout_bytes, _ = await process.communicate()
            output_text = stdout_bytes.decode("utf-8", errors="ignore") if stdout_bytes else ""

            # Count generated PDFs from the output
            pdf_count = output_text.lower().count("success")

            return {
                "success": process.returncode == 0,
                "pdf_count": pdf_count,
                "output": output_text,
            }
        except Exception as e:
            return {"success": False, "pdf_count": 0, "output": str(e)}

    def kill_active_batch(self) -> bool:
        """Terminate active batch execution."""
        if not self.active_batch or not self.active_batch.is_running:
            return False
        try:
            self.active_batch.process.terminate()
            return True
        except Exception:
            try:
                self.active_batch.process.kill()
                return True
            except Exception:
                return False

# Global PipelineManager instance
pipeline_manager = PipelineManager()
