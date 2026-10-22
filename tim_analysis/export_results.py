import argparse
from datetime import datetime
import glob
import os
import re
import shutil
import sys
import tempfile
import pdfkit
from fpdf import FPDF
from PIL import Image
import toml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from cloud.gcs_helper import gcs_sync_down, gcs_sync_up, is_gcs_uri, join_uri


# --- PDF Class with Enhanced Styling ---
class PDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4', title='', subject_info=''):
        super().__init__(orientation, unit, format)
        self.doc_title = title
        self.subject_info = subject_info
        self.set_auto_page_break(auto=True, margin=15)
        self.header_color = (34, 54, 104)
        self.body_color = (0, 0, 0)

    def header(self):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(*self.header_color)
        self.cell(0, 10, self.doc_title, 0, 1, 'C')
        self.set_font('Arial', '', 10)
        self.cell(0, 5, self.subject_info, 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')
        self.set_x(-50)
        self.cell(0, 10, datetime.now().strftime("%Y-%m-%d"), 0, 0, 'R')

    def section_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.set_text_color(*self.header_color)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(2)

    def section_body(self, text):
        self.set_font('Arial', '', 10)
        self.set_text_color(*self.body_color)
        self.multi_cell(0, 5, text)
        self.ln()


# --- PDF Generation Functions ---
def convert_html_to_pdf(html_path, pdf_path):
    try:
        print(f"Converting {html_path} to {pdf_path}...")
        pdfkit.from_file(html_path, pdf_path, options={'enable-local-file-access': ''})
        print("  -> Success.")
    except Exception as e:
        print(f"  -> Failed to convert file. Error: {e}")


def create_pdf_from_images(image_folder, pdf_path, title, subject_info, description=""):
    images = [
        p for p in sorted(glob.glob(os.path.join(image_folder, '*')))
        if p.lower().endswith(('.png', '.jpg', '.jpeg'))
    ]
    if not images:
        print(f"No images found in {image_folder}")
        return

    print(f"Creating {pdf_path}...")
    pdf = PDF(title=title, subject_info=subject_info)
    pdf.add_page()
    if description:
        pdf.section_title("Description")
        pdf.section_body(description)

    y_coord = pdf.get_y()
    for image_path in images:
        try:
            with Image.open(image_path) as img:
                w, h = img.size
                pdf_width = 190  # Content width
                pdf_height = pdf_width * h / w

                if y_coord + pdf_height > 270:
                    pdf.add_page()
                    y_coord = pdf.get_y()

                pdf.image(image_path, x=10, y=y_coord, w=pdf_width)
                y_coord += pdf_height + 5
        except Exception as e:
            print(f"  -> Failed to process image {image_path}. Error: {e}")

    pdf.output(pdf_path)
    print("  -> Success.")


def create_glm_results_pdf(image_folder, pdf_path, title, subject_info, model_config):
    images = sorted(glob.glob(os.path.join(image_folder, '*.jpg'))) or sorted(glob.glob(os.path.join(image_folder, '*.png')))
    if not images:
        print(f"No images found in {image_folder}")
        return

    print(f"Creating {pdf_path}...")
    pdf = PDF(title=title, subject_info=subject_info)
    pdf.add_page()

    pdf.section_title("Analysis Model Summary")
    pdf.section_body(
        f"Description: {model_config.get('description', 'N/A')}\n"
        f"Basis Function: {model_config.get('basis', 'N/A')}"
    )

    image_groups = {}
    for image_path in images:
        filename = os.path.basename(image_path)
        prefix = re.split(r'[._]', filename)[0]
        if prefix not in image_groups:
            image_groups[prefix] = []
        image_groups[prefix].append(image_path)

    for prefix, group_images in image_groups.items():
        pdf.add_page()

        contrast_info = next((g for g in model_config.get("glt", []) if g["label"] == prefix), None)
        contrast_sym = f"Contrast: {contrast_info['sym']}" if contrast_info else ""

        pdf.section_title(f"Contrast: {prefix}")
        if contrast_sym:
            pdf.section_body(contrast_sym)

        if len(group_images) == 3:
            page_width = 190
            total_aspect_ratio = 0
            img_dims = []
            for image_path in group_images:
                with Image.open(image_path) as img:
                    w, h = img.size
                    img_dims.append((w, h))
                    total_aspect_ratio += w / h

            common_height = page_width / total_aspect_ratio

            x = 10
            y = pdf.get_y()
            for i, image_path in enumerate(group_images):
                w, h = img_dims[i]
                new_width = common_height * w / h
                try:
                    pdf.image(image_path, x=x, y=y, w=new_width, h=common_height)
                    x += new_width
                except Exception as e:
                    print(f"  -> Failed to process image {image_path}. Error: {e}")
            pdf.ln(common_height + 5)
        else:
            y = pdf.get_y()
            for image_path in group_images:
                try:
                    with Image.open(image_path) as img:
                        w, h = img.size
                        pdf_width = 190
                        pdf_height = pdf_width * h / w
                        if y + pdf_height > 270:
                            pdf.add_page()
                            y = pdf.get_y()
                        pdf.image(image_path, x=10, y=y, w=pdf_width)
                        y += pdf_height + 5
                except Exception as e:
                    print(f"  -> Failed to process image {image_path}. Error: {e}")

    pdf.output(pdf_path)
    print("  -> Success.")


def main():
    parser = argparse.ArgumentParser(description="Export MRI analysis results to PDF.")
    parser.add_argument("--output_dir", help="Analysis output directory (local path or gs:// URI). Defaults to path in config.")
    parser.add_argument("--dropbox_dir", default=os.path.expanduser("~/Dropbox"), help="Directory or gs:// URI to save exported PDFs.")
    parser.add_argument("--subject", nargs="+", help="Specific subject IDs to export. If omitted, all subjects are exported.")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        main_config = toml.load(os.path.join(base_dir, "analysis_configs", "main_config.toml"))
        analysis_models = toml.load(os.path.join(base_dir, "analysis_configs", "analysis_models.toml"))
    except FileNotFoundError as e:
        print(f"Error: Configuration file not found. {e}")
        return

    output_dir = args.output_dir or os.environ.get("MRI_OUTPUT_DIR") or main_config.get("output_dir")
    if not output_dir:
        print("Error: output_dir not specified in args or config.")
        return

    dest_root = os.environ.get("MRI_REPORTS_DIR") or args.dropbox_dir

    subjects_configs = main_config.get("subjects")
    if not subjects_configs and "all_subjects" in main_config:
        subjects_configs = [{"id": s, "group": "TIM", "sessions": [{"id": 1}]} for s in main_config["all_subjects"]]

    if not subjects_configs:
        print("No subjects found in configuration.")
        return

    if args.subject:
        subjects_configs = [s for s in subjects_configs if s["id"] in args.subject]
        if not subjects_configs:
            print(f"No matching subjects found for: {args.subject}")
            return

    tmp_work_dir = tempfile.mkdtemp(prefix="afni_export_") if (is_gcs_uri(output_dir) or is_gcs_uri(dest_root)) else None

    try:
        for subject_config in subjects_configs:
            subject_id = subject_config["id"]
            subject_group = subject_config.get("group", "N/A")
            print(f"--- Processing subject: {subject_id} (Group: {subject_group}) ---")

            for session_config in subject_config.get("sessions", [{"id": 1}]):
                session_id = f"ses-{session_config['id']}"
                print(f"  - Processing session: {session_id} -")

                if is_gcs_uri(output_dir):
                    session_folder = os.path.join(tmp_work_dir, "in", subject_id, session_id)
                    gcs_session_uri = join_uri(output_dir, subject_id, session_id)
                    # Exclude heavy .BRIK / .nii files when staging down just for QC PDF generation
                    if not gcs_sync_down(gcs_session_uri, session_folder, exclude_regex=r".*\.(BRIK|nii)(\.gz)?$"):
                        continue
                else:
                    session_folder = os.path.join(output_dir, subject_id, session_id)
                    if not os.path.isdir(session_folder):
                        continue

                if is_gcs_uri(dest_root):
                    dest_folder = os.path.join(tmp_work_dir, "out", subject_id, session_id)
                else:
                    dest_folder = os.path.join(dest_root, subject_id, session_id)
                os.makedirs(dest_folder, exist_ok=True)

                subject_info_str = f"Subject: {subject_id} | Session: {session_id} | Group: {subject_group}"

                html_path = os.path.join(session_folder, "func_preproc", f"{subject_id}_preproc.results", f"QC_{subject_id}_preproc", "index.html")
                if os.path.exists(html_path):
                    pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_preproc_QC.pdf")
                    convert_html_to_pdf(html_path, pdf_path)

                anat_warped_folder = os.path.join(session_folder, "anat_warped")
                if os.path.isdir(anat_warped_folder):
                    pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_anatomical_QC.pdf")
                    create_pdf_from_images(anat_warped_folder, pdf_path, "Anatomical QC Report", subject_info_str, "Results of anatomical data warping to MNI space.")

                glm_base_folder = os.path.join(session_folder, "glm")
                if os.path.isdir(glm_base_folder):
                    for analysis_name, model_config in analysis_models.items():
                        analysis_folder = os.path.join(glm_base_folder, analysis_name)
                        if not os.path.isdir(analysis_folder):
                            continue

                        print(f"    - Processing analysis: {analysis_name} -")

                        glm_qc_media_folder = os.path.join(analysis_folder, f"{subject_id}_{analysis_name}.results", f"QC_{subject_id}_{analysis_name}", "media")
                        if os.path.isdir(glm_qc_media_folder):
                            pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_{analysis_name}_QC.pdf")
                            create_pdf_from_images(glm_qc_media_folder, pdf_path, f"GLM QC: {analysis_name}", subject_info_str, "Quality control metrics from the AFNI preprocessing and GLM pipeline.")

                        glm_results_qc_folder = os.path.join(analysis_folder, "QC")
                        if os.path.isdir(glm_results_qc_folder):
                            pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_{analysis_name}_results.pdf")
                            create_glm_results_pdf(glm_results_qc_folder, pdf_path, f"GLM Results: {analysis_name}", subject_info_str, model_config)

                if is_gcs_uri(dest_root):
                    gcs_dest_uri = join_uri(dest_root, subject_id, session_id)
                    print(f"    - Uploading exported PDFs to {gcs_dest_uri} -")
                    gcs_sync_up(dest_folder, gcs_dest_uri)
                if is_gcs_uri(output_dir):
                    shutil.rmtree(session_folder, ignore_errors=True)
    finally:
        if tmp_work_dir and os.path.exists(tmp_work_dir):
            shutil.rmtree(tmp_work_dir, ignore_errors=True)

    print("--- All processing complete ---")


if __name__ == "__main__":
    main()
