"""
Google Cloud Storage (GCS) staging, zip extraction, and task-sharding utilities
for the Abend Lab fMRI Analysis Pipelines (TIM & WAR).

Supports both `gcloud storage` / `gsutil` CLI acceleration (parallel composite/sliced
transfers) and the Python `google-cloud-storage` SDK as a fallback.
"""

import fnmatch
import glob
import logging
import os
import re
import shutil
import subprocess
import zipfile
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def is_gcs_uri(path: Optional[str]) -> bool:
    """
    Return True if path is a Google Cloud Storage URI starting with 'gs://'.

    Parameters
    ----------
    path : Optional[str]
        URI or path string to inspect.

    Returns
    -------
    bool
        True if path starts with 'gs://', False otherwise.
    """
    return bool(path and str(path).strip().startswith("gs://"))


def normalize_gcs_uri(uri: str) -> str:
    """
    Strip leading/trailing whitespace and trailing slashes from a GCS URI or local path.
    Preserves the 'gs://' scheme boundary for root URIs like 'gs://' or 'gs:///'.

    Parameters
    ----------
    uri : str
        URI or path string to normalize.

    Returns
    -------
    str
        Cleaned URI or path without trailing slashes.
    """
    stripped = str(uri).strip()
    if stripped.startswith("gs://"):
        body = stripped[len("gs://"):].rstrip("/")
        return f"gs://{body}"
    return stripped.rstrip("/")


def join_uri(base: str, *parts: str) -> str:
    """
    Join URI or filesystem path components cleanly without duplicate slashes.

    Parameters
    ----------
    base : str
        Base URI (e.g. 'gs://bucket') or local directory path.
    *parts : str
        Subdirectory, filename, or prefix components to append.

    Returns
    -------
    str
        Properly concatenated URI or filesystem path.
    """
    if is_gcs_uri(base):
        cleaned = [normalize_gcs_uri(base)]
        for p in parts:
            p_clean = str(p).strip("/")
            if p_clean:
                cleaned.append(p_clean)
        return "/".join(cleaned)
    return os.path.join(base, *parts)


def get_cloud_task_shard() -> Tuple[Optional[int], Optional[int]]:
    """
    Detect if running inside a Google Cloud Batch or Cloud Run Job task array.

    Inspects BATCH_TASK_INDEX/BATCH_TASK_COUNT and
    CLOUD_RUN_TASK_INDEX/CLOUD_RUN_TASK_COUNT environment variables.

    Returns
    -------
    Tuple[Optional[int], Optional[int]]
        (task_index, task_count) or (None, None) if running normally/locally.
    """
    idx_str = os.environ.get("BATCH_TASK_INDEX") or os.environ.get("CLOUD_RUN_TASK_INDEX")
    cnt_str = os.environ.get("BATCH_TASK_COUNT") or os.environ.get("CLOUD_RUN_TASK_COUNT")
    if idx_str is not None and cnt_str is not None:
        try:
            return int(idx_str), int(cnt_str)
        except ValueError:
            pass
    return None, None


def shard_subjects_for_cloud_task(subjects: List[str], console: Optional[Any] = None) -> List[str]:
    """
    If running in a multi-task Cloud Batch / Cloud Run Job (where task_count > 1),
    filter the subject list so each task processes its assigned slice `subjects[idx::total]`.

    Parameters
    ----------
    subjects : List[str]
        Full list of candidate subject IDs.
    console : Optional[Any]
        Optional Rich console or logger instance for diagnostic output.

    Returns
    -------
    List[str]
        Partitioned subject subset for the current task shard, or full list if single-task.
    """
    idx, total = get_cloud_task_shard()
    if idx is not None and total is not None and total > 1:
        sharded = subjects[idx::total]
        if console:
            console.log(
                f"[bold magenta]Cloud Task Shard Detected:[/] Task {idx + 1}/{total} "
                f"assigned {len(sharded)}/{len(subjects)} subject(s): {sharded}"
            )
        return sharded
    return subjects


def _has_gcloud_storage() -> bool:
    """Return True if `gcloud` CLI executable is available on PATH."""
    return shutil.which("gcloud") is not None


def _parse_gcs_uri(gcs_uri: str) -> Tuple[str, str]:
    """
    Split gs://bucket/prefix/object into (bucket_name, blob_prefix).

    Parameters
    ----------
    gcs_uri : str
        Google Cloud Storage URI to parse.

    Returns
    -------
    Tuple[str, str]
        (bucket_name, blob_prefix) without leading slash.
    """
    stripped = str(gcs_uri).strip()
    if stripped.startswith("gs://"):
        without_scheme = stripped[len("gs://"):]
    else:
        without_scheme = stripped.lstrip("/")
    parts = without_scheme.split("/", 1)
    bucket_name = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    return bucket_name, prefix


def gcs_path_exists(gcs_uri: str) -> bool:
    """
    Check whether an object or directory prefix exists in GCS.

    Parameters
    ----------
    gcs_uri : str
        Target GCS URI to check.

    Returns
    -------
    bool
        True if the object or at least one blob with the given prefix exists.
    """
    gcs_uri = normalize_gcs_uri(gcs_uri)
    if _has_gcloud_storage():
        res = subprocess.run(
            ["gcloud", "storage", "ls", gcs_uri],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if res.returncode == 0:
            return True

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket_name, prefix = _parse_gcs_uri(gcs_uri)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(prefix)
        if blob.exists():
            return True
        blobs = list(client.list_blobs(bucket_name, prefix=prefix.rstrip("/") + "/", max_results=1))
        return len(blobs) > 0
    except Exception:
        return False


def gcs_download_file(gcs_uri: str, local_dest: str) -> bool:
    """
    Download a single object from GCS to local_dest.

    Parameters
    ----------
    gcs_uri : str
        Source GCS URI of the object.
    local_dest : str
        Local filesystem destination path.

    Returns
    -------
    bool
        True if download succeeded and local file exists, False otherwise.
    """
    os.makedirs(os.path.dirname(os.path.abspath(local_dest)), exist_ok=True)
    if _has_gcloud_storage():
        res = subprocess.run(
            ["gcloud", "storage", "cp", gcs_uri, local_dest],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        if res.returncode == 0 and os.path.exists(local_dest):
            return True

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return False
        blob.download_to_filename(local_dest)
        return os.path.exists(local_dest)
    except Exception as e:
        logger.warning("GCS download failed for %s: %s", gcs_uri, e)
        return False


def gcs_upload_file(local_src: str, gcs_uri: str) -> bool:
    """
    Upload a single local file to GCS.

    Parameters
    ----------
    local_src : str
        Local filesystem source path.
    gcs_uri : str
        Destination GCS URI.

    Returns
    -------
    bool
        True if upload succeeded, False otherwise.
    """
    if not os.path.exists(local_src):
        return False
    if _has_gcloud_storage():
        res = subprocess.run(
            ["gcloud", "storage", "cp", local_src, gcs_uri],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        if res.returncode == 0:
            return True

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket_name, blob_name = _parse_gcs_uri(gcs_uri)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_src)
        return True
    except Exception as e:
        logger.warning("GCS upload failed for %s: %s", gcs_uri, e)
        return False


def gcs_sync_down(gcs_prefix: str, local_dir: str, exclude_regex: Optional[str] = None) -> bool:
    """
    Recursively sync a GCS directory prefix down to a local directory.

    Parameters
    ----------
    gcs_prefix : str
        Source GCS prefix URI.
    local_dir : str
        Local destination directory path.
    exclude_regex : Optional[str]
        Optional regular expression for paths to exclude.

    Returns
    -------
    bool
        True if sync succeeded, False otherwise.
    """
    gcs_prefix = normalize_gcs_uri(gcs_prefix)
    os.makedirs(local_dir, exist_ok=True)

    if _has_gcloud_storage():
        cmd = ["gcloud", "storage", "rsync", "-r"]
        if exclude_regex:
            cmd.extend(["--exclude", exclude_regex])
        cmd.extend([gcs_prefix, local_dir])
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        if res.returncode == 0 and os.listdir(local_dir):
            return True

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket_name, prefix = _parse_gcs_uri(gcs_prefix)
        prefix_slash = prefix.rstrip("/") + "/" if prefix else ""
        blobs = list(client.list_blobs(bucket_name, prefix=prefix_slash))
        if not blobs:
            return False
        pattern = re.compile(exclude_regex) if exclude_regex else None
        for blob in blobs:
            rel_path = blob.name[len(prefix_slash):] if prefix_slash else blob.name
            if not rel_path or rel_path.endswith("/"):
                continue
            if pattern and pattern.search(rel_path):
                continue
            dest_path = os.path.join(local_dir, rel_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            blob.download_to_filename(dest_path)
        return True
    except Exception as e:
        logger.warning("GCS sync down failed for %s: %s", gcs_prefix, e)
        return False


def gcs_sync_up(local_dir: str, gcs_prefix: str, exclude_regex: Optional[str] = None) -> bool:
    """
    Recursively sync a local directory up to a GCS prefix.

    Attempts high-speed CLI acceleration using `gcloud storage rsync -r`.
    Falls back cleanly to the Python `google.cloud.storage` SDK with complete
    exception handling.

    Parameters
    ----------
    local_dir : str
        Source local directory to sync from.
    gcs_prefix : str
        Target GCS URI prefix.
    exclude_regex : Optional[str]
        Optional regular expression for paths to exclude.

    Returns
    -------
    bool
        True if sync succeeded, False otherwise.
    """
    if not os.path.exists(local_dir):
        return False
    gcs_prefix = normalize_gcs_uri(gcs_prefix)

    if _has_gcloud_storage():
        cmd = ["gcloud", "storage", "rsync", "-r"]
        if exclude_regex:
            cmd.extend(["--exclude", exclude_regex])
        cmd.extend([local_dir, gcs_prefix])
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        if res.returncode == 0:
            return True

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket_name, prefix = _parse_gcs_uri(gcs_prefix)
        bucket = client.bucket(bucket_name)
        prefix_slash = prefix.rstrip("/") + "/" if prefix else ""
        pattern = re.compile(exclude_regex) if exclude_regex else None

        for root, _, files in os.walk(local_dir):
            for fname in files:
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, local_dir).replace(os.sep, "/")
                if pattern and pattern.search(rel_path):
                    continue
                blob = bucket.blob(prefix_slash + rel_path)
                blob.upload_from_filename(full_path)
        return True
    except Exception as e:
        logger.warning("GCS sync up failed for %s: %s", gcs_prefix, e)
        return False


def gcs_download_wildcard(gcs_pattern: str, local_dir: str) -> bool:
    """
    Download files matching a wildcard pattern (e.g. gs://.../stats.sub-435+tlrc.*) to local_dir.

    Parameters
    ----------
    gcs_pattern : str
        GCS pattern with glob wildcards (*, ?).
    local_dir : str
        Target local directory.

    Returns
    -------
    bool
        True if at least one file was matched and downloaded, False otherwise.
    """
    os.makedirs(local_dir, exist_ok=True)
    if _has_gcloud_storage():
        res = subprocess.run(
            ["gcloud", "storage", "cp", gcs_pattern, local_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        if res.returncode == 0:
            return True

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket_name, pattern_prefix = _parse_gcs_uri(gcs_pattern)
        base_prefix = pattern_prefix.split("*")[0].split("[")[0]
        blobs = list(client.list_blobs(bucket_name, prefix=base_prefix))
        matched = False
        for blob in blobs:
            if fnmatch.fnmatch(blob.name, pattern_prefix):
                dest = os.path.join(local_dir, os.path.basename(blob.name))
                blob.download_to_filename(dest)
                matched = True
        return matched
    except Exception as e:
        logger.warning("GCS wildcard download failed for %s: %s", gcs_pattern, e)
        return False


def extract_subject_zip(zip_path: str, subject_id: str, dest_input_root: str) -> str:
    """
    Extract a subject's input zip file into `dest_input_root` ensuring
    `{dest_input_root}/{subject_id}/ses-X/...` is guaranteed to exist regardless
    of archive layout:
      1. Root folder is `{subject_id}/...`
      2. Root folder is `ses-X/...`
      3. BIDS modality folders (`anat/`, `func/`, `fmap/`, `dwi/`, `beh/`) at root
      4. Arbitrary nested paths.

    Strips `__MACOSX` metadata automatically.

    Parameters
    ----------
    zip_path : str
        Path to local .zip archive.
    subject_id : str
        Subject ID string (e.g. 'sub-435').
    dest_input_root : str
        Destination root folder for inputs.

    Returns
    -------
    str
        Path to active subject directory: `{dest_input_root}/{subject_id}`.
    """
    subject_target_dir = os.path.join(dest_input_root, subject_id)
    os.makedirs(dest_input_root, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if not n.startswith("__MACOSX") and not n.endswith("/")]
        top_levels = {n.split("/")[0] for n in names if "/" in n}

        if top_levels == {subject_id}:
            # Zip already has `sub-XXX/...` at the root
            zf.extractall(dest_input_root)
        elif top_levels and all(t.startswith("ses-") for t in top_levels):
            # Zip has `ses-1/...` directly at root -> extract into dest_input_root/sub-XXX/
            os.makedirs(subject_target_dir, exist_ok=True)
            zf.extractall(subject_target_dir)
        elif top_levels and top_levels.issubset({"anat", "func", "fmap", "dwi", "beh"}):
            # Zip has `anat/` and `func/` directly at root -> extract into dest_input_root/sub-XXX/ses-1/
            ses1_dir = os.path.join(subject_target_dir, "ses-1")
            os.makedirs(ses1_dir, exist_ok=True)
            zf.extractall(ses1_dir)
        else:
            # Extract to a temporary dir and inspect structure
            tmp_extract = os.path.join(dest_input_root, f"_tmp_{subject_id}")
            shutil.rmtree(tmp_extract, ignore_errors=True)
            zf.extractall(tmp_extract)

            nested_subj = os.path.join(tmp_extract, subject_id)
            if os.path.isdir(nested_subj):
                if os.path.exists(subject_target_dir):
                    shutil.rmtree(subject_target_dir)
                shutil.move(nested_subj, subject_target_dir)
                shutil.rmtree(tmp_extract, ignore_errors=True)
            else:
                if os.path.exists(subject_target_dir):
                    shutil.rmtree(subject_target_dir)
                shutil.move(tmp_extract, subject_target_dir)

    return subject_target_dir


def stage_in_subject_input(
    subject_id: str,
    configured_input_dir: str,
    scratch_root: str,
    console: Optional[Any] = None,
) -> str:
    """
    Ensure the raw BIDS input directory for `subject_id` is available locally.
    - If `configured_input_dir` is a `gs://` URI:
      1. Looks for `{configured_input_dir}/{subject_id}.zip` first.
      2. Falls back to `{configured_input_dir}/{subject_id}/` directory in GCS.
    - If `configured_input_dir` is a local directory:
      1. If `{configured_input_dir}/{subject_id}` exists as a directory, uses `configured_input_dir`.
      2. If `{configured_input_dir}/{subject_id}.zip` exists locally, extracts it into `{scratch_root}/input`.

    Returns the active local `input_dir` root path containing `{subject_id}/`.

    Parameters
    ----------
    subject_id : str
        Subject ID (e.g. 'sub-435').
    configured_input_dir : str
        Input directory path or GCS URI from main_config.toml.
    scratch_root : str
        Fast local scratch directory for staging and extraction.
    console : Optional[Any]
        Optional Rich console or logger.

    Returns
    -------
    str
        Local directory path containing `{subject_id}/`.

    Raises
    ------
    FileNotFoundError
        If neither zip nor uncompressed directory is found in GCS.
    """
    local_input_root = os.path.join(scratch_root, "input")
    local_subj_dir = os.path.join(local_input_root, subject_id)

    if is_gcs_uri(configured_input_dir):
        if os.path.isdir(local_subj_dir) and os.listdir(local_subj_dir):
            return local_input_root

        os.makedirs(local_input_root, exist_ok=True)
        gcs_zip_uri = join_uri(configured_input_dir, f"{subject_id}.zip")
        local_zip_path = os.path.join(local_input_root, f"{subject_id}.zip")

        if console:
            console.log(f"[cyan]Staging in input for {subject_id} from GCS ({gcs_zip_uri})...[/]")

        if gcs_download_file(gcs_zip_uri, local_zip_path):
            if console:
                console.log(f"[dim]Extracting {local_zip_path} to {local_input_root}...[/]")
            extract_subject_zip(local_zip_path, subject_id, local_input_root)
            os.remove(local_zip_path)
            return local_input_root

        # Fallback: check if uncompressed folder exists in GCS
        gcs_dir_uri = join_uri(configured_input_dir, subject_id)
        if console:
            console.log(f"[dim]Zip not found; trying uncompressed GCS folder {gcs_dir_uri}...[/]")
        if gcs_sync_down(gcs_dir_uri, local_subj_dir):
            return local_input_root

        raise FileNotFoundError(
            f"Could not find {gcs_zip_uri} or {gcs_dir_uri} in Google Cloud Storage."
        )

    # Local input_dir mode: check if subject exists as a `.zip` file inside local input_dir
    direct_subj_dir = os.path.join(configured_input_dir, subject_id)
    direct_subj_zip = os.path.join(configured_input_dir, f"{subject_id}.zip")
    if not os.path.isdir(direct_subj_dir) and os.path.isfile(direct_subj_zip):
        if not os.path.isdir(local_subj_dir) or not os.listdir(local_subj_dir):
            if console:
                console.log(f"[cyan]Extracting local archive {direct_subj_zip} to {local_input_root}...[/]")
            extract_subject_zip(direct_subj_zip, subject_id, local_input_root)
        return local_input_root

    return configured_input_dir


def cleanup_pb00_to_pb04(
    func_preproc_dir: str,
    subject_id: str,
    console: Optional[Any] = None,
) -> int:
    """
    Delete heavy intermediate AFNI preprocessing bricks (`pb00`..`pb04` and `all_runs`)
    from `{func_preproc_dir}/{subject_id}_preproc.results` while keeping `pb05.*.scale+tlrc`,
    motion/outlier `.1D` files, anatomical followers, masks, and `QC_*` reports.

    Parameters
    ----------
    func_preproc_dir : str
        Parent preprocessing output directory.
    subject_id : str
        Subject ID string.
    console : Optional[Any]
        Optional Rich console or logger.

    Returns
    -------
    int
        Number of intermediate brick files removed.
    """
    results_dir = os.path.join(func_preproc_dir, f"{subject_id}_preproc.results")
    if not os.path.isdir(results_dir):
        return 0

    patterns = [
        "pb00.*",
        "pb01.*",
        "pb02.*",
        "pb03.*",
        "pb04.*",
        "all_runs.*",
        "rm.*",
    ]
    removed_count = 0
    for pat in patterns:
        for fpath in glob.glob(os.path.join(results_dir, pat)):
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                    removed_count += 1
                except OSError:
                    pass

    if removed_count > 0 and console:
        console.log(
            f"[dim]Cleaned {removed_count} intermediate pb00-pb04/all_runs brick files for {subject_id}[/]"
        )
    return removed_count
