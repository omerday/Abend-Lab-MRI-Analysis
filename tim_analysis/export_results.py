import os
import glob
import re
import pdfkit
from fpdf import FPDF
from PIL import Image
import argparse
from datetime import datetime
import toml

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
    images = sorted(glob.glob(os.path.join(image_folder, '*')))
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
    parser.add_argument("--output_dir", help="Analysis output directory. Defaults to path in config.")
    parser.add_argument("--dropbox_dir", default=os.path.expanduser("~/Dropbox"), help="Directory to save exported PDFs.")
    args = parser.parse_args()

    try:
        main_config = toml.load("analysis_configs/main_config.toml")
        analysis_models = toml.load("analysis_configs/analysis_models.toml")
    except FileNotFoundError as e:
        print(f"Error: Configuration file not found. {e}")
        return

    # Use output_dir from config if not provided in args
    output_dir = args.output_dir if args.output_dir else main_config.get("output_dir")

    if not output_dir:
        print("Error: output_dir not specified in args or config.")
        return

    # Iterate over all subjects in config
    for subject_id in main_config.get("all_subjects", []):
        print(f"--- Processing subject: {subject_id} ---")

        subject_folder = os.path.join(output_dir, subject_id)
        if not os.path.isdir(subject_folder):
             print(f"  Subject folder not found: {subject_folder}")
             continue

        # Find sessions
        session_folders = sorted(glob.glob(os.path.join(subject_folder, 'ses-*')))
        if not session_folders:
            print(f"  No sessions found for {subject_id}")
            continue

        for session_folder in session_folders:
            session_id = os.path.basename(session_folder)
            print(f"  - Processing session: {session_id} -")

            dest_folder = os.path.join(args.dropbox_dir, subject_id, session_id)
            os.makedirs(dest_folder, exist_ok=True)
            
            subject_info_str = f"Subject: {subject_id} | Session: {session_id}"

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
                    if not os.path.isdir(analysis_folder): continue
                    
                    print(f"    - Processing analysis: {analysis_name} -")
                    
                    glm_qc_media_folder = os.path.join(analysis_folder, f"{subject_id}_{analysis_name}.results", f"QC_{subject_id}_{analysis_name}", "media")
                    if os.path.isdir(glm_qc_media_folder):
                        pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_{analysis_name}_QC.pdf")
                        create_pdf_from_images(glm_qc_media_folder, pdf_path, f"GLM QC: {analysis_name}", subject_info_str, "Quality control metrics from the AFNI preprocessing and GLM pipeline.")

                    glm_results_qc_folder = os.path.join(analysis_folder, "QC")
                    if os.path.isdir(glm_results_qc_folder):
                        pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_{analysis_name}_results.pdf")
                        create_glm_results_pdf(glm_results_qc_folder, pdf_path, f"GLM Results: {analysis_name}", subject_info_str, model_config)

    print("--- All processing complete ---")

if __name__ == "__main__":
    main()
