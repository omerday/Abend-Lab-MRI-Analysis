import os
import glob
import argparse
from pypdf import PdfWriter

def main():
    parser = argparse.ArgumentParser(description="Concatenate individual PDF reports into a single file.")
    parser.add_argument("--dropbox_dir", default=os.path.expanduser("~/Dropbox"), help="The base directory where the individual reports are saved.")
    parser.add_argument("--output_file", default="consolidated_report.pdf", help="The name of the final concatenated PDF file.")
    args = parser.parse_args()

    dropbox_dir = args.dropbox_dir
    output_file = os.path.join(dropbox_dir, args.output_file)

    if not os.path.isdir(dropbox_dir):
        print(f"Error: Dropbox directory not found at {dropbox_dir}")
        return

    merger = PdfWriter()
    report_files_to_merge = []

    print("Scanning for reports to concatenate...")

    subject_folders = sorted(glob.glob(os.path.join(dropbox_dir, 'sub-*')))

    for subject_folder in subject_folders:
        subject_id = os.path.basename(subject_folder)
        print(f"  - Found subject: {subject_id}")

        for session_name in sorted(os.listdir(subject_folder)):
            session_folder = os.path.join(subject_folder, session_name)
            if not os.path.isdir(session_folder) or not session_name.startswith('ses-'):
                continue
            
            print(f"    - Processing session: {session_name}")

            # 1. Anatomical QC
            anat_qc_path = os.path.join(session_folder, f"{subject_id}_{session_name}_anatomical_QC.pdf")
            if os.path.exists(anat_qc_path):
                report_files_to_merge.append(anat_qc_path)

            # 2. Preproc QC
            preproc_qc_path = os.path.join(session_folder, f"{subject_id}_{session_name}_preproc_QC.pdf")
            if os.path.exists(preproc_qc_path):
                report_files_to_merge.append(preproc_qc_path)

            # Find all analysis names for this session
            analysis_names = sorted([
                f.split(f"{subject_id}_{session_name}_")[1].replace("_QC.pdf", "")
                for f in glob.glob(os.path.join(session_folder, f"*_QC.pdf"))
                if "_preproc_" not in f and "_anatomical_" not in f
            ])

            for analysis_name in analysis_names:
                # 3. Analysis QC
                analysis_qc_path = os.path.join(session_folder, f"{subject_id}_{session_name}_{analysis_name}_QC.pdf")
                if os.path.exists(analysis_qc_path):
                    report_files_to_merge.append(analysis_qc_path)

                # 4. Analysis Results
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

    print("--- Concatenation complete! ---")

if __name__ == "__main__":
    main()
