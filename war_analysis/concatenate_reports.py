import argparse
import glob
import os
import shutil
import sys
import tempfile
from pypdf import PdfWriter

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from cloud.gcs_helper import gcs_sync_down, gcs_upload_file, is_gcs_uri, join_uri


def main():
    parser = argparse.ArgumentParser(description="Concatenate individual PDF reports into a single file.")
    parser.add_argument(
        "--dropbox_dir",
        default=os.path.expanduser("~/Dropbox"),
        help="The base directory or gs:// URI where the individual reports are saved.",
    )
    parser.add_argument("--output_file", default="consolidated_report.pdf", help="The name of the final concatenated PDF file.")
    args = parser.parse_args()

    raw_dropbox_dir = os.environ.get("MRI_REPORTS_DIR") or args.dropbox_dir
    tmp_dir = None

    try:
        if is_gcs_uri(raw_dropbox_dir):
            tmp_dir = tempfile.mkdtemp(prefix="afni_concat_")
            print(f"Syncing reports from {raw_dropbox_dir} to temporary folder...")
            gcs_sync_down(raw_dropbox_dir, tmp_dir)
            dropbox_dir = tmp_dir
        else:
            dropbox_dir = raw_dropbox_dir

        output_file = os.path.join(dropbox_dir, args.output_file)

        if not os.path.isdir(dropbox_dir):
            print(f"Error: Reports directory not found at {dropbox_dir}")
            return

        merger = PdfWriter()
        report_files_to_merge = []

        print("Scanning for reports to concatenate...")

        subject_folders = glob.glob(os.path.join(dropbox_dir, "sub-AL*"))
        subject_folders.extend(glob.glob(os.path.join(dropbox_dir, "sub-MD*")))
        subject_folders = sorted(subject_folders)

        for subject_folder in subject_folders:
            subject_id = os.path.basename(subject_folder)
            print(f"  - Found subject: {subject_id}")

            for session_name in sorted(os.listdir(subject_folder)):
                session_folder = os.path.join(subject_folder, session_name)
                if not os.path.isdir(session_folder) or not session_name.startswith("ses-"):
                    continue

                print(f"    - Processing session: {session_name}")

                anat_qc_path = os.path.join(session_folder, f"{subject_id}_{session_name}_anatomical_QC.pdf")
                if os.path.exists(anat_qc_path):
                    report_files_to_merge.append(anat_qc_path)

                preproc_qc_path = os.path.join(session_folder, f"{subject_id}_{session_name}_preproc_QC.pdf")
                if os.path.exists(preproc_qc_path):
                    report_files_to_merge.append(preproc_qc_path)

                analysis_names = sorted(
                    [
                        f.split(f"{subject_id}_{session_name}_")[1].replace("_QC.pdf", "")
                        for f in glob.glob(os.path.join(session_folder, "*_QC.pdf"))
                        if "_preproc_" not in f and "_anatomical_" not in f
                    ]
                )

                for analysis_name in analysis_names:
                    analysis_qc_path = os.path.join(session_folder, f"{subject_id}_{session_name}_{analysis_name}_QC.pdf")
                    if os.path.exists(analysis_qc_path):
                        report_files_to_merge.append(analysis_qc_path)

                    analysis_results_path = os.path.join(session_folder, f"{subject_id}_{session_name}_{analysis_name}_results.pdf")
                    if os.path.exists(analysis_results_path):
                        report_files_to_merge.append(analysis_results_path)

        if not report_files_to_merge:
            print("No PDF reports found to merge.")
            return

        print("\nConcatenating the following files in order:")
        for f in report_files_to_merge:
            print(f"  -> {os.path.relpath(f, dropbox_dir)}")
            merger.append(f)

        print(f"\nWriting consolidated report to: {output_file}")
        merger.write(output_file)
        merger.close()

        if is_gcs_uri(raw_dropbox_dir):
            gcs_out_uri = join_uri(raw_dropbox_dir, args.output_file)
            print(f"Uploading consolidated report to {gcs_out_uri}...")
            gcs_upload_file(output_file, gcs_out_uri)

        print("--- Concatenation complete! ---")
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
