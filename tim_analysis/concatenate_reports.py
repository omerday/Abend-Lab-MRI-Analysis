"""Multi-subject PDF QC report consolidator for the TIM pipeline.

Collects anatomical, preprocessing, and first-level GLM QC and results PDF reports
across all subjects and sessions, merging them into a single consolidated PDF document.
Supports local file systems and Google Cloud Storage (gs://) paths.
"""

import argparse
import glob
import os
import shutil
import sys
import tempfile
from typing import List, Optional

try:
    from pypdf import PdfWriter
except ImportError:
    PdfWriter = None

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from cloud.gcs_helper import gcs_sync_down, gcs_upload_file, is_gcs_uri, join_uri


def collect_tim_report_files(reports_dir: str) -> List[str]:
    """Scan directory for TIM subject reports and return ordered list of PDF files to merge.

    Traverses subject folders matching 'sub-*' and their 'ses-*' subdirectories.
    Orders files: anatomical QC, preprocessing QC, then analysis-specific QC and results.

    Args:
        reports_dir: Path to local directory containing exported reports.

    Returns:
        List of absolute paths to PDF report files in merge order.
    """
    report_files: List[str] = []
    subject_folders = sorted(glob.glob(os.path.join(reports_dir, "sub-*")))

    for subject_folder in subject_folders:
        if not os.path.isdir(subject_folder):
            continue
        subject_id = os.path.basename(subject_folder)
        print(f"  - Found subject: {subject_id}")

        for session_name in sorted(os.listdir(subject_folder)):
            session_folder = os.path.join(subject_folder, session_name)
            if not os.path.isdir(session_folder) or not session_name.startswith("ses-"):
                continue

            print(f"    - Processing session: {session_name}")

            anat_qc = os.path.join(session_folder, f"{subject_id}_{session_name}_anatomical_QC.pdf")
            if os.path.isfile(anat_qc):
                report_files.append(anat_qc)

            preproc_qc = os.path.join(session_folder, f"{subject_id}_{session_name}_preproc_QC.pdf")
            if os.path.isfile(preproc_qc):
                report_files.append(preproc_qc)

            analysis_names = sorted(
                [
                    f.split(f"{subject_id}_{session_name}_")[1].replace("_QC.pdf", "")
                    for f in glob.glob(os.path.join(session_folder, "*_QC.pdf"))
                    if "_preproc_" not in f and "_anatomical_" not in f
                ]
            )

            for analysis_name in analysis_names:
                qc_path = os.path.join(session_folder, f"{subject_id}_{session_name}_{analysis_name}_QC.pdf")
                if os.path.isfile(qc_path):
                    report_files.append(qc_path)

                results_path = os.path.join(
                    session_folder, f"{subject_id}_{session_name}_{analysis_name}_results.pdf"
                )
                if os.path.isfile(results_path):
                    report_files.append(results_path)

    return report_files


def merge_pdf_files(pdf_paths: List[str], output_path: str) -> None:
    """Merge a sequence of PDF files into a single destination file.

    Args:
        pdf_paths: List of file paths to merge.
        output_path: Destination path for merged PDF.

    Raises:
        RuntimeError: If pypdf is not installed.
        ValueError: If pdf_paths is empty.
    """
    if PdfWriter is None:
        raise RuntimeError("pypdf is required for concatenating PDF reports but is not installed.")

    if not pdf_paths:
        raise ValueError("No PDF paths provided to merge.")

    merger = PdfWriter()
    try:
        for fpath in pdf_paths:
            merger.append(fpath)

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        merger.write(output_path)
    finally:
        merger.close()


def concatenate_reports(
    reports_location: str,
    output_filename: str = "consolidated_report.pdf",
) -> Optional[str]:
    """Execute end-to-end report concatenation from local directory or GCS URI.

    Args:
        reports_location: Local directory or gs:// URI where reports reside.
        output_filename: File name for the consolidated PDF.

    Returns:
        Path or URI of the final consolidated report, or None if no reports were found.
    """
    tmp_dir: Optional[str] = None
    try:
        if is_gcs_uri(reports_location):
            tmp_dir = tempfile.mkdtemp(prefix="afni_concat_")
            print(f"Syncing reports from {reports_location} to temporary folder...")
            gcs_sync_down(reports_location, tmp_dir)
            active_dir = tmp_dir
        else:
            active_dir = reports_location

        if not os.path.isdir(active_dir):
            print(f"Error: Reports directory not found at {active_dir}", file=sys.stderr)
            return None

        print("Scanning for reports to concatenate...")
        report_files = collect_tim_report_files(active_dir)
        if not report_files:
            print("No PDF reports found to merge.")
            return None

        print(f"\nConcatenating {len(report_files)} report file(s) in order:")
        for f in report_files:
            print(f"  -> {os.path.relpath(f, active_dir)}")

        output_file = os.path.join(active_dir, output_filename)
        print(f"\nWriting consolidated report to: {output_file}")
        merge_pdf_files(report_files, output_file)

        if is_gcs_uri(reports_location):
            gcs_out_uri = join_uri(reports_location, output_filename)
            print(f"Uploading consolidated report to {gcs_out_uri}...")
            gcs_upload_file(output_file, gcs_out_uri)
            final_target = gcs_out_uri
        else:
            final_target = output_file

        print("--- Concatenation complete! ---")
        return final_target
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for report concatenation."""
    parser = argparse.ArgumentParser(description="Concatenate individual PDF reports into a single file.")
    parser.add_argument(
        "--dropbox_dir",
        default=os.path.expanduser("~/Dropbox"),
        help="The base directory or gs:// URI where the individual reports are saved.",
    )
    parser.add_argument(
        "--output_file",
        default="consolidated_report.pdf",
        help="The name of the final concatenated PDF file.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for concatenate_reports."""
    args = parse_args(argv)
    reports_dir = os.environ.get("MRI_REPORTS_DIR") or args.dropbox_dir
    res = concatenate_reports(reports_dir, output_filename=args.output_file)
    return 0 if res is not None else 1


if __name__ == "__main__":
    sys.exit(main())
