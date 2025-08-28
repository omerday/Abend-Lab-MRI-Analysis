import pdfkit
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--subject", help="Subject ID, in the format of sub-xx.")
args = parser.parse_args()

subject = args.subject
if subject:
    html_path = f"{subject}.results/QC_{subject}/index.html"
    pdf_path = f"{subject}.results/QC_{subject}/index.pdf"
    options = {'enable-local-file-access': ''}
    pdfkit.from_file(html_path, pdf_path, options=options)

options = {'enable-local-file-access': ''}

print(f"Searching for index.html files in current directory...")

for dirpath, _, filenames in os.walk(os.getcwd()):
    if 'index.html' in filenames:
        html_path = os.path.join(dirpath, 'index.html')
        pdf_path = os.path.join(dirpath, 'index.pdf')
        print(f"Found: {html_path}")
        try:
            print(f"Converting to {pdf_path}...")
            pdfkit.from_file(html_path, pdf_path, options=options)
            print("  -> Success.")
        except Exception as e:
            print(f"  -> Failed to convert file. Error: {e}")

print("\nProcessing complete.")