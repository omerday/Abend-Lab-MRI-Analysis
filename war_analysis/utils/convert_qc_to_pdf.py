"""Headless HTML-to-PDF QC report converter for WAR pipeline.

Converts AFNI APQC (afni_proc.py Quality Control) HTML reports into PDF format
using pdfkit and wkhtmltopdf.
"""

import argparse
import os
import sys
from typing import Dict, List, Optional

try:
    import pdfkit
except ImportError:
    pdfkit = None


DEFAULT_PDFKIT_OPTIONS: Dict[str, str] = {
    "enable-local-file-access": "",
}


def convert_html_to_pdf(
    html_path: str,
    pdf_path: str,
    options: Optional[Dict[str, str]] = None,
) -> bool:
    """Convert an individual HTML report to PDF using pdfkit.

    Args:
        html_path: Path to the source HTML file.
        pdf_path: Destination path for the converted PDF file.
        options: Optional pdfkit conversion options. Defaults to enabling local file access.

    Returns:
        True if conversion succeeded, False otherwise.

    Raises:
        FileNotFoundError: If the source HTML file does not exist.
        RuntimeError: If pdfkit is not installed.
    """
    if pdfkit is None:
        raise RuntimeError("pdfkit is not installed. Cannot convert HTML to PDF.")

    if not os.path.isfile(html_path):
        raise FileNotFoundError(f"Source HTML file does not exist: {html_path}")

    opts = options or DEFAULT_PDFKIT_OPTIONS
    out_dir = os.path.dirname(pdf_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    try:
        pdfkit.from_file(html_path, pdf_path, options=opts)
        return True
    except Exception as exc:
        print(f"Failed to convert {html_path} to {pdf_path}: {exc}", file=sys.stderr)
        return False


def convert_subject_qc(
    subject: str,
    base_dir: str = ".",
    options: Optional[Dict[str, str]] = None,
) -> bool:
    """Convert the AFNI QC report for a specific subject.

    Looks for {subject}.results/QC_{subject}/index.html in base_dir.

    Args:
        subject: Subject identifier (e.g. 'sub-AL01').
        base_dir: Base directory containing subject results folders.
        options: Optional pdfkit conversion options.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    html_path = os.path.join(base_dir, f"{subject}.results", f"QC_{subject}", "index.html")
    pdf_path = os.path.join(base_dir, f"{subject}.results", f"QC_{subject}", "index.pdf")

    if not os.path.isfile(html_path):
        print(f"QC HTML report not found for subject {subject}: {html_path}", file=sys.stderr)
        return False

    print(f"Converting QC report for {subject}: {html_path} -> {pdf_path}...")
    success = convert_html_to_pdf(html_path, pdf_path, options=options)
    if success:
        print(f"Successfully converted QC report for {subject}.")
    else:
        print(f"Failed to convert QC report for {subject}.", file=sys.stderr)
    return success


def convert_all_qc_reports(
    root_dir: str = ".",
    options: Optional[Dict[str, str]] = None,
) -> int:
    """Recursively search for and convert all index.html reports under root_dir.

    Args:
        root_dir: Root directory path to walk.
        options: Optional pdfkit conversion options.

    Returns:
        Count of successfully converted PDF files.
    """
    opts = options or DEFAULT_PDFKIT_OPTIONS
    converted_count = 0
    print(f"Searching for index.html files in {root_dir}...")

    for dirpath, _, filenames in os.walk(root_dir):
        if "index.html" in filenames:
            html_path = os.path.join(dirpath, "index.html")
            pdf_path = os.path.join(dirpath, "index.pdf")
            print(f"Found: {html_path}")
            print(f"Converting to {pdf_path}...")
            try:
                if convert_html_to_pdf(html_path, pdf_path, options=opts):
                    print("  -> Success.")
                    converted_count += 1
                else:
                    print("  -> Failed to convert file.", file=sys.stderr)
            except Exception as exc:
                print(f"  -> Failed to convert file. Error: {exc}", file=sys.stderr)

    print(f"\nProcessing complete. Converted {converted_count} file(s).")
    return converted_count


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: List of arguments. If None, sys.argv[1:] is used.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Convert AFNI APQC HTML quality control reports to PDF."
    )
    parser.add_argument(
        "--subject",
        default=None,
        help="Subject ID, in the format of sub-xx. If omitted, searches directory for all index.html files.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for convert_qc_to_pdf.

    Args:
        argv: Optional list of CLI arguments.

    Returns:
        Exit code: 0 on success, non-zero on failure.
    """
    args = parse_args(argv)

    if args.subject:
        success = convert_subject_qc(args.subject)
        return 0 if success else 1

    convert_all_qc_reports(os.getcwd())
    return 0


if __name__ == "__main__":
    sys.exit(main())