"""Export WAR analysis results and AFNI QC reports to PDF format.

Converts APQC HTML reports and generates consolidated image-based PDFs
(anatomical normalization, GLM activation maps, contrast t-statistic overlays)
for distribution and archiving. Supports local filesystem destinations and
Google Cloud Storage (gs://) buckets.
"""

import argparse
from datetime import datetime
import glob
import os
import re
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional

try:
    import pdfkit
except ImportError:
    pdfkit = None

try:
    from fpdf import FPDF
except ImportError:
    class FPDF:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import toml
except ImportError:
    import tomllib as toml  # type: ignore

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from cloud.gcs_helper import gcs_sync_down, gcs_sync_up, is_gcs_uri, join_uri


class PDF(FPDF):
    """Custom FPDF document generator with standardized header, footer, and styling."""

    def __init__(
        self,
        orientation: str = "P",
        unit: str = "mm",
        format: str = "A4",
        title: str = "",
        subject_info: str = "",
    ) -> None:
        super().__init__(orientation, unit, format)
        self.doc_title = title
        self.subject_info = subject_info
        if hasattr(self, "set_auto_page_break"):
            self.set_auto_page_break(auto=True, margin=15)
        self.header_color = (34, 54, 104)
        self.body_color = (0, 0, 0)

    def header(self) -> None:
        """Render document header with title and subject metadata."""
        if not hasattr(self, "set_font"):
            return
        self.set_font("Arial", "B", 14)
        self.set_text_color(*self.header_color)
        self.cell(0, 10, self.doc_title, 0, 1, "C")
        self.set_font("Arial", "", 10)
        self.cell(0, 5, self.subject_info, 0, 1, "C")
        self.ln(5)

    def footer(self) -> None:
        """Render document footer with page number and execution date."""
        if not hasattr(self, "set_y"):
            return
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(128)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")
        self.set_x(-50)
        self.cell(0, 10, datetime.now().strftime("%Y-%m-%d"), 0, 0, "R")

    def section_title(self, title: str) -> None:
        """Render a styled section heading."""
        if not hasattr(self, "set_font"):
            return
        self.set_font("Arial", "B", 12)
        self.set_text_color(*self.header_color)
        self.cell(0, 10, title, 0, 1, "L")
        self.ln(2)

    def section_body(self, text: str) -> None:
        """Render a body paragraph with standardized line height and margins."""
        if not hasattr(self, "set_font"):
            return
        self.set_font("Arial", "", 10)
        self.set_text_color(*self.body_color)
        self.multi_cell(0, 5, text)
        self.ln()


def convert_html_to_pdf(html_path: str, pdf_path: str) -> bool:
    """Convert an individual HTML report to PDF using pdfkit.

    Args:
        html_path: Source HTML file path.
        pdf_path: Target PDF destination file path.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    if pdfkit is None:
        print(f"Skipping HTML conversion for {html_path}: pdfkit is not installed.", file=sys.stderr)
        return False

    out_dir = os.path.dirname(pdf_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    try:
        print(f"Converting {html_path} to {pdf_path}...")
        pdfkit.from_file(html_path, pdf_path, options={"enable-local-file-access": ""})
        print("  -> Success.")
        return True
    except Exception as exc:
        print(f"  -> Failed to convert file. Error: {exc}", file=sys.stderr)
        return False


def create_pdf_from_images(
    image_folder: str,
    pdf_path: str,
    title: str,
    subject_info: str,
    description: str = "",
) -> bool:
    """Assemble a PDF document from all PNG/JPG images in a folder.

    Args:
        image_folder: Directory containing input images.
        pdf_path: Output PDF destination path.
        title: Document title.
        subject_info: Subject metadata string.
        description: Optional introductory text.

    Returns:
        True if PDF was generated successfully, False otherwise.
    """
    if Image is None:
        print(f"Skipping image PDF creation for {pdf_path}: PIL is not installed.", file=sys.stderr)
        return False

    images = [
        p for p in sorted(glob.glob(os.path.join(image_folder, "*")))
        if p.lower().endswith((".png", ".jpg", ".jpeg"))
    ]
    if not images:
        print(f"No images found in {image_folder}")
        return False

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
                pdf_width = 190.0  # Printable width in mm
                pdf_height = pdf_width * h / w

                if y_coord + pdf_height > 270:
                    pdf.add_page()
                    y_coord = pdf.get_y()

                pdf.image(image_path, x=10, y=y_coord, w=pdf_width)
                y_coord += pdf_height + 5
        except Exception as exc:
            print(f"  -> Failed to process image {image_path}. Error: {exc}", file=sys.stderr)

    out_dir = os.path.dirname(pdf_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    pdf.output(pdf_path)
    print("  -> Success.")
    return True


def create_glm_results_pdf(
    image_folder: str,
    pdf_path: str,
    title: str,
    subject_info: str,
    model_config: Dict[str, Any],
) -> bool:
    """Generate GLM statistical contrast activation results PDF with 3-slice montages.

    Args:
        image_folder: Directory containing generated @chauffeur_afni slices.
        pdf_path: Output PDF destination path.
        title: Document title.
        subject_info: Subject metadata string.
        model_config: Model dictionary containing 'description', 'basis', and 'glt' contrast metadata.

    Returns:
        True if PDF was created successfully, False otherwise.
    """
    if Image is None:
        print(f"Skipping GLM results PDF for {pdf_path}: PIL is not installed.", file=sys.stderr)
        return False

    images = sorted(glob.glob(os.path.join(image_folder, "*.jpg"))) or sorted(glob.glob(os.path.join(image_folder, "*.png")))
    if not images:
        print(f"No images found in {image_folder}")
        return False

    print(f"Creating {pdf_path}...")
    pdf = PDF(title=title, subject_info=subject_info)
    pdf.add_page()

    pdf.section_title("Analysis Model Summary")
    pdf.section_body(
        f"Description: {model_config.get('description', 'N/A')}\n"
        f"Basis Function: {model_config.get('basis', 'N/A')}"
    )

    image_groups: Dict[str, List[str]] = {}
    for image_path in images:
        filename = os.path.basename(image_path)
        prefix = re.split(r"[._]", filename)[0]
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
            page_width = 190.0
            total_aspect_ratio = 0.0
            img_dims = []
            for image_path in group_images:
                with Image.open(image_path) as img:
                    w, h = img.size
                    img_dims.append((w, h))
                    total_aspect_ratio += w / h

            common_height = page_width / total_aspect_ratio if total_aspect_ratio > 0 else 60.0

            x = 10.0
            y = pdf.get_y()
            for i, image_path in enumerate(group_images):
                w, h = img_dims[i]
                new_width = common_height * w / h
                try:
                    pdf.image(image_path, x=x, y=y, w=new_width, h=common_height)
                    x += new_width
                except Exception as exc:
                    print(f"  -> Failed to process image {image_path}. Error: {exc}", file=sys.stderr)
            pdf.ln(common_height + 5)
        else:
            y = pdf.get_y()
            for image_path in group_images:
                try:
                    with Image.open(image_path) as img:
                        w, h = img.size
                        pdf_width = 190.0
                        pdf_height = pdf_width * h / w
                        if y + pdf_height > 270:
                            pdf.add_page()
                            y = pdf.get_y()
                        pdf.image(image_path, x=10, y=y, w=pdf_width)
                        y += pdf_height + 5
                except Exception as exc:
                    print(f"  -> Failed to process image {image_path}. Error: {exc}", file=sys.stderr)

    out_dir = os.path.dirname(pdf_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    pdf.output(pdf_path)
    print("  -> Success.")
    return True


def export_subject_results(
    subject_config: Dict[str, Any],
    output_dir: str,
    dest_root: str,
    analysis_models: Dict[str, Any],
    tmp_work_dir: Optional[str] = None,
) -> None:
    """Export QC and GLM results for an individual WAR subject across all sessions."""
    subject_id = subject_config["id"]
    subject_group = subject_config.get("group", "N/A")
    print(f"--- Processing subject: {subject_id} (Group: {subject_group}) ---")

    for session_config in subject_config.get("sessions", []):
        session_id = f"ses-{session_config['id']}"
        print(f"  - Processing session: {session_id} -")

        if is_gcs_uri(output_dir) and tmp_work_dir:
            session_folder = os.path.join(tmp_work_dir, "in", subject_id, session_id)
            gcs_session_uri = join_uri(output_dir, subject_id, session_id)
            if not gcs_sync_down(gcs_session_uri, session_folder, exclude_regex=r".*\.(BRIK|nii)(\.gz)?$"):
                continue
        else:
            session_folder = os.path.join(output_dir, subject_id, session_id)
            if not os.path.isdir(session_folder):
                continue

        if is_gcs_uri(dest_root) and tmp_work_dir:
            dest_folder = os.path.join(tmp_work_dir, "out", subject_id, session_id)
        else:
            dest_folder = os.path.join(dest_root, subject_id, session_id)
        os.makedirs(dest_folder, exist_ok=True)

        subject_info_str = f"Subject: {subject_id} | Session: {session_id} | Group: {subject_group}"

        # 1. Preprocessing APQC report
        html_path = os.path.join(
            session_folder,
            "func_preproc",
            f"{subject_id}_preproc.results",
            f"QC_{subject_id}_preproc",
            "index.html",
        )
        if os.path.exists(html_path):
            pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_preproc_QC.pdf")
            convert_html_to_pdf(html_path, pdf_path)

        # 2. Anatomical SSW warping QC
        anat_warped_folder = os.path.join(session_folder, "anat_warped")
        if os.path.isdir(anat_warped_folder):
            pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_anatomical_QC.pdf")
            create_pdf_from_images(
                anat_warped_folder,
                pdf_path,
                "Anatomical QC Report",
                subject_info_str,
                "Results of anatomical data warping to MNI space.",
            )

        # 3. GLM QC and Results
        glm_base_folder = os.path.join(session_folder, "glm")
        if os.path.isdir(glm_base_folder):
            for analysis_name, model_config in analysis_models.items():
                analysis_folder = os.path.join(glm_base_folder, analysis_name)
                if not os.path.isdir(analysis_folder):
                    continue

                print(f"    - Processing analysis: {analysis_name} -")
                glm_qc_media = os.path.join(
                    analysis_folder,
                    f"{subject_id}_{analysis_name}.results",
                    f"QC_{subject_id}_{analysis_name}",
                    "media",
                )
                if os.path.isdir(glm_qc_media):
                    pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_{analysis_name}_QC.pdf")
                    create_pdf_from_images(
                        glm_qc_media,
                        pdf_path,
                        f"GLM QC: {analysis_name}",
                        subject_info_str,
                        "Quality control metrics from the AFNI preprocessing and GLM pipeline.",
                    )

                glm_results_qc = os.path.join(analysis_folder, "QC")
                if os.path.isdir(glm_results_qc):
                    pdf_path = os.path.join(dest_folder, f"{subject_id}_{session_id}_{analysis_name}_results.pdf")
                    create_glm_results_pdf(
                        glm_results_qc,
                        pdf_path,
                        f"GLM Results: {analysis_name}",
                        subject_info_str,
                        model_config,
                    )

        if is_gcs_uri(dest_root):
            gcs_dest_uri = join_uri(dest_root, subject_id, session_id)
            print(f"    - Uploading exported PDFs to {gcs_dest_uri} -")
            gcs_sync_up(dest_folder, gcs_dest_uri)

        if is_gcs_uri(output_dir):
            shutil.rmtree(session_folder, ignore_errors=True)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for export_results."""
    parser = argparse.ArgumentParser(description="Export MRI analysis results to PDF.")
    parser.add_argument(
        "--output_dir",
        help="Analysis output directory (local path or gs:// URI). Defaults to path in config.",
    )
    parser.add_argument(
        "--dropbox_dir",
        default=os.path.expanduser("~/Dropbox"),
        help="Directory or gs:// URI to save exported PDFs.",
    )
    parser.add_argument(
        "--subject",
        nargs="+",
        help="Specific subject IDs to export. If omitted, all subjects are exported.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for export_results."""
    args = parse_args(argv)
    base_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        main_config_path = os.path.join(base_dir, "analysis_configs", "main_config.toml")
        models_config_path = os.path.join(base_dir, "analysis_configs", "analysis_models.toml")
        main_config = toml.load(main_config_path) if hasattr(toml, "load") else toml.loads(open(main_config_path).read())
        analysis_models = toml.load(models_config_path) if hasattr(toml, "load") else toml.loads(open(models_config_path).read())
    except Exception as exc:
        print(f"Error loading configuration files: {exc}", file=sys.stderr)
        return 1

    output_dir = args.output_dir or os.environ.get("MRI_OUTPUT_DIR") or main_config.get("output_dir")
    if not output_dir:
        print("Error: output_dir not specified in args or config.", file=sys.stderr)
        return 1

    dest_root = os.environ.get("MRI_REPORTS_DIR") or args.dropbox_dir
    subjects_list = main_config.get("subjects", [])

    if not subjects_list:
        print("No subjects found in configuration.", file=sys.stderr)
        return 1

    if args.subject:
        subjects_list = [s for s in subjects_list if s["id"] in args.subject]
        if not subjects_list:
            print(f"No matching subjects found for: {args.subject}", file=sys.stderr)
            return 1

    tmp_work_dir = (
        tempfile.mkdtemp(prefix="afni_export_")
        if (is_gcs_uri(output_dir) or is_gcs_uri(dest_root))
        else None
    )

    try:
        for subj_conf in subjects_list:
            export_subject_results(
                subject_config=subj_conf,
                output_dir=output_dir,
                dest_root=dest_root,
                analysis_models=analysis_models,
                tmp_work_dir=tmp_work_dir,
            )
        print("--- All processing complete ---")
        return 0
    finally:
        if tmp_work_dir and os.path.exists(tmp_work_dir):
            shutil.rmtree(tmp_work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())