"""
The script goes over the given subject ID, and changing the folders and file names from sub-xx to sub-1xx
"""

import os
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("subject", help="Subject ID, in the format of sub-xx")
args = parser.parse_args()

subject = args.subject
if not subject:
    print("No subject provided. Quitting.")
    quit()

if not subject.startswith("sub-"):
    print("Wrong subject format. Should be sub-xx. Quitting.")
    quit()

if subject not in os.listdir():
    print(f"folder {subject} not found.")

old_id = subject.split('-')[-1]
new_subject = "".join(["sub-", "1", old_id])

os.rename(subject, new_subject)
sessions = [ses for ses in os.listdir(new_subject) if "ses-" in ses]
folders = ['anat', 'func', 'fmap', 'dwi']

for session in sessions:
    print(f"Going over session {session}")
    for folder in folders:
        if folder in os.listdir(f"{new_subject}/{session}"):
            print(f"Going over folder {folder}")
            path = "".join([new_subject, '/', session, '/', folder])
            for file in os.listdir(path):
                if subject in file:
                    new_file_name = file.replace(subject, new_subject)
                    print(f'Found file {file}. Renaming to {new_file_name}.')
                    os.rename(path + '/' + file, path + '/' + new_file_name)

