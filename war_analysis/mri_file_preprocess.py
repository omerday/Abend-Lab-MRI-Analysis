import os
import argparse
import subprocess
from collections import defaultdict
import pandas as pd

DCM_CONVERTER_PATH = "dcm2niix"

"""
See dcm2niix installation guide here - https://github.com/rordenlab/dcm2niix
If necessary, change the DCM_CONVERTER path to match the installation path you need.
"""

NIFTI_SUFFIX = ".nii.gz"
JSON_SUFFIX = ".json"
BVAL_SUFFIX = ".bval"
BVEC_SUFFIX = ".bvec"

SUFFIXES = [".nii.gz", ".json", ".bval", ".bvec"]
ECHOES = {"_e1": "echo-1",
          "_e2": "echo-2",
          "_e3": "echo-3"}

def get_suffix(file_name: str) -> str:
    for suffix in SUFFIXES:
        if file_name.endswith(suffix):
            return suffix[1:]
    print(f"In get_suffix({file_name}). Couldn't recognize file structure. Quitting.")
    quit()

def get_echo(file_name: str) -> str:
    for echo in ECHOES.keys():
        if echo in file_name:
            return ECHOES[echo]
    print(f"In get_echo({file_name}). Couldn't recognize file echo. Quitting.")
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
    current_files_in_path = os.listdir(fmap_path)
    # NOTE - we're combining two magnitudes into 1. If we don't want to do so, we need to remove '-m y' from the command
    # and catch this case in the naming as well (as magnitude2).
    print(subprocess.run(f'{DCM_CONVERTER_PATH} -f "%p_%s" -m y -p y -z y -o {fmap_path} ./FIELDMAP', shell=True))
    for file in os.listdir(fmap_path):
        if file not in current_files_in_path:
            print(f"Handling file {file}")
            if "fieldmap_" not in file:
                print("File is not a fieldmap file! Skipping.")
                continue
            suffix = get_suffix(file)
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
    current_files_in_path = os.listdir(t1_path)
    print(subprocess.run(f'{DCM_CONVERTER_PATH} -f "%p_%s" -p y -z y -o {t1_path} ./T1', shell=True))
    for file in os.listdir(t1_path):
        if file not in current_files_in_path:
            print(f"Handling file {file}")
            if "t1_mprage" not in file:
                print("File is not a T1. Skipping.")
                continue
            suffix = get_suffix(file)
            new_name = f"{subject}_{session}_T1w.{suffix}"
            print(f"Renaming file to {new_name}")
            os.rename(f"{t1_path}/{file}", f"{t1_path}/{new_name}")
else:
    print("No T1 files to process. Moving on.")

# Handle ANATOMY files
if os.path.exists("./ANATOMY"):
    print("Starting conversion of FLAIR scans")
    anat_path = f"./{session}/anat"
    if not os.path.exists(anat_path):
        os.mkdir(anat_path)
    current_files_in_path = os.listdir(anat_path)
    print(subprocess.run(f'{DCM_CONVERTER_PATH} -f "%p_%s" -p y -z y -o {anat_path} ./T1', shell=True))
    for file in os.listdir(anat_path):
        if file not in current_files_in_path:
            print(f"Handling file {file}")
            suffix = get_suffix(file)
            new_name = f"{subject}_{session}_FLAIR.{suffix}"
            print(f"Renaming file to {new_name}")
            os.rename(f"{anat_path}/{file}", f"{anat_path}/{new_name}")
else:
    print("No FLAIR files to process. Moving on.")

#Handle DTI files
if os.path.exists("./DTI"):
    print("Starting conversion of DTI scans")
    dwi_path = f"./{session}/dwi"
    if not os.path.exists(dwi_path):
        os.mkdir(dwi_path)
    current_files_in_path = os.listdir(dwi_path)
    print(subprocess.run(f'{DCM_CONVERTER_PATH} -f "%p_%s" -p y -z y -o {dwi_path} ./DTI', shell=True))
    suffix_numbers = defaultdict(int)
    # A DTI run should produce 4 files - nifti, json, bval and bvec.
    # If one of those isn't present, we shouldn't proceed.
    for file in os.listdir(dwi_path):
        suffix_numbers[file.split(".")[0].split("_")[-1]] += 1
    for file in os.listdir(dwi_path):
        if file not in current_files_in_path:
            suffix = get_suffix(file)
            old_name = file.split(".")[0]
            if suffix_numbers[old_name.split("_")[-1]] == 4:
                print(f"handling file {file}")
                if "ep2d_diff" not in file:
                    print("Not a DTI file. Skipping")
                    continue
                new_name = f"{subject}_{session}_dwi_{'pa' if '_PA_' in old_name else 'ap'}.{suffix}"
                print(f"renaming file to {new_name}")
                os.rename(f"{dwi_path}/{file}", f"{dwi_path}/{new_name}")
            else:
                print(f"file {file} doesn't have 4 of the same enumaration ({old_name.split('_')[-1]}). Deleting.")
                os.remove(f"{dwi_path}/{file}")
else:
    print("No DTI files to process. Moving on.")

# Handle RS-MRI files
if os.path.exists("./REST"):
    print("Starting conversion of RS scans")
    func_path = f"./{session}/func"
    if not os.path.exists(func_path):
        os.mkdir(func_path)
    current_files_in_path = os.listdir(func_path)
    print(subprocess.run(f'{DCM_CONVERTER_PATH} -f "%p_%s" -p y -z y -o {func_path} ./REST', shell=True))
    for file in os.listdir(func_path):
        if file not in current_files_in_path:
            print(f"Handling file {file}")
            if "CBU_REST" not in file:
                print("Not an RS scan. Skipping")
                continue
            suffix = get_suffix(file)
            echo = get_echo(file)
            new_name = f"{subject}_{session}_task-rest_{echo}_bold.{suffix}"
            print(f"Renaming file to {new_name}")
            os.rename(f"{func_path}/{file}", f"{func_path}/{new_name}")
else:
    print("No RS files to process. Moving on.")

# Handle WAR Files
# MAKE SURE FOLDER IS IN FORMAT WARX AND NOT WAR_X
for war_run in range(1, 3):
    malformatted_war_folder = f"./WAR {war_run}"
    war_folder = f"./WAR{war_run}"
    if os.path.exists(malformatted_war_folder):
        os.rename(malformatted_war_folder, war_folder)
    if os.path.exists(war_folder):
        print(f"Starting conversion of WAR {war_run} scans")
        func_path = f"./{session}/func"
        current_files_in_path = []
        if not os.path.exists(func_path):
            os.mkdir(func_path)
        else:
            # The folder might contain files from RS processing.
            current_files_in_path = os.listdir(func_path)
        print(subprocess.run(f'{DCM_CONVERTER_PATH} -f "%p_%s" -p y -z y -o {func_path} {war_folder}', shell=True))
        for file in os.listdir(func_path):
            if file not in current_files_in_path:
                print(f"Handling file {file}")
                if "CBU_WAR" not in file:
                    print("Not a WAR file. Skipping")
                    continue
                suffix = get_suffix(file)
                echo = get_echo(file)
                new_name = f"{subject}_{session}_task-war_run-{war_run}_{echo}_bold.{suffix}"
                print(f"Renaming file to {new_name}")
                os.rename(f"{func_path}/{file}", f"{func_path}/{new_name}")
    else:
        print("No WAR 1 files to process. Moving on.")

# Prepare log files
print("Preparing log files")
for current_file in os.listdir():
    if current_file.startswith("WAR_LogFile"):
        print(f"Handling file {current_file}")
        if "Run_1" in current_file:
            run_number = 1
        else:
            run_number = 2
        df = pd.read_csv(current_file)
        df.drop("Unnamed: 0", axis=1, inplace=True)
        df = df.round({"Time": 2, "Duration": 2})
        new_file_name = f"{subject}_{session}_task-war_run-{run_number}_events.tsv"
        df.to_csv(f"./{session}/func/{new_file_name}", sep="\t", index=False)
        print(f"Created file {new_file_name}")