import os
import argparse
import subprocess

DCM_CONVERTER_PATH = "dcm2niix"

"""
See dcm2niix installation guide here - https://github.com/rordenlab/dcm2niix
If necessary, change the DCM_CONVERTER path to match the installation path you need.
"""

NIFTI_SUFFIX = ".nii.gz"
JSON_SUFFIX = ".json"

def choose_suffix(file_name: str) -> str:
    if file_name.endswith(NIFTI_SUFFIX):
        return NIFTI_SUFFIX[1:]
    elif file_name.endswith(JSON_SUFFIX):
        return JSON_SUFFIX[1:]
    else:
        print("Couldn't recognize file structure. Quitting.")
        quit()

parser = argparse.ArgumentParser()
parser.add_argument("subject", help="Subject ID, in the format of sub-xx")
parser.add_argument("--session", default=1, help="Session ID - 1 or 2", )
args = parser.parse_args()

subject = args.subject
if not subject:
    print("No subject provided. Quitting.")
    quit()

if not subject.startswith("sub-"):
    print("Wrong subject format. Should be sub-xx. Quitting.")
    quit()

session = ""
if not args.session:
    session = "ses-1"
else:
    try:
        ses_id = int(args.session)
        session = f"ses-{ses_id}"
    except:
        print("Something went wrong parsing the session ID. Please enter a single digit.")
        quit()

print(f"Starting conversion script for subject {subject} and session {session}")

base_path = f"./{subject}/"
try:
    os.chdir(base_path)
except:
    print(f"Folder {base_path} doesn't exist. Quitting.")

if not os.path.exists(session):
    os.mkdir(session)

# Handle FIELDMAP files
if os.path.exists("./FIELDMAP"):
    print("Starting conversion of Fieldmap scans")
    fmap_path = f"./{session}/fmap"
    if not os.path.exists(fmap_path):
        os.mkdir(fmap_path)
    print(subprocess.run(f'{DCM_CONVERTER_PATH} -f "%p_%s" -m y -p y -z y -o {fmap_path} ./FIELDMAP', shell=True))
    for file in os.listdir(fmap_path):
        print(f"Handling file {file}")
        suffix = choose_suffix(file)
        new_name = f"{subject}_{session}_run-{1 if '_PA' in file else 2}"
        if "_ph." in file:
            new_name += "_phasediff"
        else:
            new_name += "_magnitude1"
        new_name += f".{suffix}"
        print(f"Renaming file to {new_name}")
        os.rename(f"{fmap_path}/{file}", f"{fmap_path}/{new_name}")
else:
    print("No Fieldmap files to process. Moving on.")

# Handle T1 files
if os.path.exists("./T1"):
    print("Starting conversion of T1 scans")
    t1_path = f"./{session}/anat"
    if not os.path.exists(t1_path):
        os.mkdir(t1_path)
    print(subprocess.run(f'{DCM_CONVERTER_PATH} -f "%p_%s" -m y -p y -z y -o {t1_path} ./T1', shell=True))
    for file in os.listdir(t1_path):
        print(f"Handling file {file}")
        suffix = choose_suffix(file)
        new_name = f"{subject}_{session}_T1w.{suffix}"
        print(f"Renaming file to {new_name}")
        os.rename(f"{t1_path}/{file}", f"{t1_path}/{new_name}")
else:
    print("No T1 files to process. Moving on.")

#Handle DTI files
if os.path.exists("./DTI"):
    print("Starting conversion of DTI scans")
else:
    print("No DTI files to process. Moving on.")