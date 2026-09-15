import os
import glob
import time
import re
import datetime
import shutil
import subprocess
from typing import List, Dict, Any, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

def format_bytes(bytes_val: int) -> str:
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"

def format_duration(seconds: float) -> str:
    """Format seconds into human readable duration."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

def get_system_metrics(storage_paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """Collect CPU, RAM, and disk storage usage metrics with psutil or standard library fallbacks."""
    cpu_percent = 0.0
    ram_used_str = "N/A"
    ram_total_str = "N/A"
    ram_percent = 0.0

    if HAS_PSUTIL and psutil is not None:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.2)
            mem = psutil.virtual_memory()
            ram_used_str = format_bytes(mem.used)
            ram_total_str = format_bytes(mem.total)
            ram_percent = mem.percent
        except Exception:
            pass
    elif os.path.exists("/proc/meminfo"):
        try:
            # Linux /proc/meminfo fallback
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = int(parts[1].split()[0]) * 1024
            total = meminfo.get("MemTotal", 0)
            avail = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            used = total - avail
            ram_used_str = format_bytes(used)
            ram_total_str = format_bytes(total)
            ram_percent = round((used / total * 100), 1) if total else 0.0
        except Exception:
            pass

    disks = []
    seen_mounts = set()
    paths_to_check = storage_paths or ["/"]

    for path in paths_to_check:
        try:
            if not os.path.exists(path):
                continue
            usage = shutil.disk_usage(path)
            mount_key = (usage.total, usage.free)
            if mount_key in seen_mounts:
                continue
            seen_mounts.add(mount_key)

            pct_used = round((usage.used / usage.total * 100), 1) if usage.total else 0.0
            disks.append({
                "path": path,
                "total": format_bytes(usage.total),
                "used": format_bytes(usage.used),
                "free": format_bytes(usage.free),
                "percent_used": pct_used,
            })
        except Exception:
            continue

    return {
        "cpu_percent": cpu_percent,
        "ram_used": ram_used_str,
        "ram_total": ram_total_str,
        "ram_percent": ram_percent,
        "disks": disks,
    }

def get_active_afni_processes() -> List[Dict[str, Any]]:
    """Scan the system for running AFNI, Python analysis controllers, and worker scripts."""
    target_keywords = [
        "run_analysis.py", "afni_proc.py", "3dDeconvolve", "3dttest++",
        "3dLMEr", "sswarper2", "3dmask_tool", "3dClustSim", "@chauffeur_afni",
        "01_preprocess_anat.sh", "02_preprocess_func.sh", "03_run_glm.sh", "04_run_group_analysis.sh"
    ]

    active = []
    now = time.time()

    if HAS_PSUTIL and psutil is not None:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'cpu_percent', 'memory_percent']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if not cmdline:
                    continue
                cmd_str = " ".join(cmdline)

                matched_kw = next((kw for kw in target_keywords if kw in cmd_str), None)
                if not matched_kw:
                    continue

                sub_match = re.search(r'(sub-[A-Za-z0-9]+)', cmd_str)
                subject = sub_match.group(1) if sub_match else None

                analysis_match = re.search(r'--analysis\s+([A-Za-z0-9_]+)', cmd_str)
                analysis = analysis_match.group(1) if analysis_match else None

                step_match = re.search(r'--step\s+([A-Za-z0-9_]+)', cmd_str)
                step = step_match.group(1) if step_match else None

                create_time = proc.info.get('create_time') or now
                elapsed = now - create_time

                active.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "keyword": matched_kw,
                    "subject": subject,
                    "analysis": analysis,
                    "step": step,
                    "cmd_snippet": cmd_str[:120],
                    "elapsed": format_duration(elapsed),
                    "cpu_percent": proc.info.get('cpu_percent', 0.0),
                    "memory_percent": proc.info.get('memory_percent', 0.0),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    else:
        # Fallback using 'ps -eo pid,command'
        try:
            ps_res = subprocess.run(["ps", "-eo", "pid,command"], capture_output=True, text=True)
            for line in ps_res.stdout.splitlines():
                matched_kw = next((kw for kw in target_keywords if kw in line), None)
                if not matched_kw:
                    continue
                parts = line.strip().split(None, 1)
                if len(parts) < 2:
                    continue
                pid_str, cmd_str = parts[0], parts[1]
                if pid_str.isdigit():
                    pid = int(pid_str)
                    sub_match = re.search(r'(sub-[A-Za-z0-9]+)', cmd_str)
                    subject = sub_match.group(1) if sub_match else None

                    analysis_match = re.search(r'--analysis\s+([A-Za-z0-9_]+)', cmd_str)
                    analysis = analysis_match.group(1) if analysis_match else None

                    step_match = re.search(r'--step\s+([A-Za-z0-9_]+)', cmd_str)
                    step = step_match.group(1) if step_match else None

                    active.append({
                        "pid": pid,
                        "name": matched_kw,
                        "keyword": matched_kw,
                        "subject": subject,
                        "analysis": analysis,
                        "step": step,
                        "cmd_snippet": cmd_str[:120],
                        "elapsed": "Active",
                        "cpu_percent": 0.0,
                        "memory_percent": 0.0,
                    })
        except Exception:
            pass

    return active

def get_recent_logs(repo_root: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Scan log directories across tim_analysis and war_analysis and return summarized states."""
    log_patterns = [
        os.path.join(repo_root, "tim_analysis", "logs", "*.log"),
        os.path.join(repo_root, "war_analysis", "logs", "*.log"),
    ]

    all_files = []
    for pat in log_patterns:
        all_files.extend(glob.glob(pat))

    all_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    recent = []

    for fpath in all_files[:limit]:
        fname = os.path.basename(fpath)
        pipeline = "tim" if "tim_analysis" in fpath else "war"
        mtime = os.path.getmtime(fpath)
        mod_time_str = datetime.datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M")
        size_bytes = os.path.getsize(fpath)

        last_lines = []
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f if line.strip()]
                last_lines = lines[-5:] if lines else []
        except Exception:
            pass

        last_line_text = last_lines[-1] if last_lines else "Empty log file"
        full_tail = " ".join(last_lines).lower()

        if any(w in full_tail for w in ["successfully completed", "complete", "success", "script finished"]):
            status = "SUCCESS"
            status_icon = "✅"
        elif any(w in full_tail for w in ["error", "failed", "cannot", "abort", "fatal"]):
            status = "FAILED"
            status_icon = "❌"
        elif time.time() - mtime < 120:
            status = "RUNNING"
            status_icon = "⏳"
        else:
            status = "IDLE"
            status_icon = "⚪"

        sub_match = re.match(r'(sub-[A-Za-z0-9]+)', fname)
        subject = sub_match.group(1) if sub_match else fname.replace(".log", "")

        recent.append({
            "path": fpath,
            "filename": fname,
            "subject": subject,
            "pipeline": pipeline,
            "modified_time": mod_time_str,
            "size": format_bytes(size_bytes),
            "status": status,
            "icon": status_icon,
            "last_line": last_line_text[:90],
        })

    return recent
