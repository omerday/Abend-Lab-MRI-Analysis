"""
The script goes over the given subject ID, and changing the folders and file names from sub-xx to sub-1xx
"""

import os
import argparse
import shutil


parser = argparse.ArgumentParser()
parser.add_argument("subject", help="Subject ID, in the format of sub-xx")
parser.add_argument("--prefix", help="Prefix to add before ID, eg. sub-<pref>xx")
args = parser.parse_args()

subject = args.subject
prefix = args.prefix

if not subject:
    print("No subject provided. Quitting.")
    quit()

if not subject.startswith("sub-"):
    print("Wrong subject format. Should be sub-xx. Quitting.")
    quit()

if not prefix:
    print("No prefix provided. Quitting.")
    quit()

if subject not in os.listdir():
    print(f"folder {subject} not found.")

old_id = subject.split('-')[-1]
new_subject = "".join(["sub-", prefix, old_id])

try:
    os.rename(subject, new_subject)
except Exception as e:
    print(f"Failed to rename folder {subject} to {new_subject}. Error: {e}")
    
sessions = [ses for ses in os.listdir(new_subject) if "ses-" in ses]
folders = ['anat', 'func', 'fmap', 'dwi', 'anat_warped']

for session in sessions:
    print(f"Going over session {session}")
    for folder in folders:
        if folder in os.listdir(f"{new_subject}/{session}"):
            print(f"Going over folder {folder}")
            if folder == 'anat_warped':
                try:
                    shutil.rmtree(f"{new_subject}/{session}/{folder}")
                    print("File tree removed successfully")
                    continue
                except Exception as e:
                    print(f"Couldn't remove folder with error: {e}")
            path = "".join([new_subject, '/', session, '/', folder])
            for file in os.listdir(path):
                if subject in file:
                    new_file_name = file.replace(subject, new_subject)
                    print(f'Found file {file}. Renaming to {new_file_name}.')
                    os.rename(path + '/' + file, path + '/' + new_file_name)

