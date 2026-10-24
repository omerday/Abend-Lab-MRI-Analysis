"""Raw DICOM to BIDS dataset organizer and preprocessor for the TIM pipeline.

Orchestrates dcm2niix conversion of raw scanner directories (T1, ANATOMY/FLAIR,
FIELDMAP, DTI, REST, TIM) into BIDS directory hierarchies, aligns event onset files,
and generates initial Ledalab ERA timing files.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from typing import Dict, List, Optional

import pandas as pd

# Pipeline-local import (maintaining directory isolation)
import era_to_timing

DCM_CONVERTER_PATH = "dcm2niix"

NIFTI_SUFFIX = ".nii.gz"
JSON_SUFFIX = ".json"
BVAL_SUFFIX = ".bval"
BVEC_SUFFIX = ".bvec"

SUFFIXES = [".nii.gz", ".json", ".bval", ".bvec"]
ECHOES: Dict[str, str] = {
    "_e1": "echo-1",
    "_e2": "echo-2",
    "_e3": "echo-3",
}


def get_suffix(file_name: str) -> str:
    """Extract known neuroimaging file extension suffix without leading period.

    Args:
        file_name: File name to inspect.

    Returns:
        Suffix string (e.g. 'nii.gz', 'json').

    Raises:
        ValueError: If file does not end with a recognized neuroimaging suffix.
    """
    for suffix in SUFFIXES:
        if file_name.endswith(suffix):
            return suffix[1:]
    raise ValueError(f"Could not recognize neuroimaging file suffix for: {file_name}")


def get_echo(file_name: str) -> str:
    """Extract multi-echo label from file name.

    Args:
        file_name: File name containing echo token (_e1, _e2, _e3).

    Returns:
        Standard BIDS echo string (e.g. 'echo-1').

    Raises:
        ValueError: If no known echo token is present in file_name.
    """
    for echo_key, echo_val in ECHOES.items():
        if echo_key in file_name:
            return echo_val
    raise ValueError(f"Could not recognize multi-echo identifier in: {file_name}")


def convert_fieldmap(
    subj_dir: str,
    subject: str,
    session: str,
    converter: str = DCM_CONVERTER_PATH,
) -> None:
    """Convert raw FIELDMAP DICOM directory to BIDS fmap structure."""
    fmap_src = os.path.join(subj_dir, "FIELDMAP")
    if not os.path.exists(fmap_src):
        print("No Fieldmap files to process. Moving on.")
        return

    print("Starting conversion of Fieldmap scans...")
    fmap_dest = os.path.join(subj_dir, session, "fmap")
    os.makedirs(fmap_dest, exist_ok=True)
    existing_files = set(os.listdir(fmap_dest))

    cmd = [converter, "-f", "%p_%s", "-m", "y", "-p", "y", "-z", "y", "-o", fmap_dest, fmap_src]
    subprocess.run(cmd, check=False)

    for file in os.listdir(fmap_dest):
        if file not in existing_files:
            if "fieldmap_" not in file:
                print(f"File {file} is not a fieldmap scan. Skipping.")
                continue
            suffix = get_suffix(file)
            run_num = 1 if "_PA" in file else 2
            suffix_desc = "_phasediff" if "_ph." in file else "_magnitude1"
            new_name = f"{subject}_{session}_run-{run_num}{suffix_desc}.{suffix}"
            os.rename(os.path.join(fmap_dest, file), os.path.join(fmap_dest, new_name))


def convert_t1(
    subj_dir: str,
    subject: str,
    session: str,
    converter: str = DCM_CONVERTER_PATH,
) -> None:
    """Convert raw T1 DICOM directory to BIDS anat T1w structure."""
    t1_src = os.path.join(subj_dir, "T1")
    if not os.path.exists(t1_src):
        print("No T1 files to process. Moving on.")
        return

    print("Starting conversion of T1 scans...")
    anat_dest = os.path.join(subj_dir, session, "anat")
    os.makedirs(anat_dest, exist_ok=True)
    existing_files = set(os.listdir(anat_dest))

    cmd = [converter, "-f", "%p_%s", "-p", "y", "-z", "y", "-o", anat_dest, t1_src]
    subprocess.run(cmd, check=False)

    for file in os.listdir(anat_dest):
        if file not in existing_files:
            if "t1_mprage" not in file:
                print(f"File {file} is not a T1 scan. Skipping.")
                continue
            suffix = get_suffix(file)
            new_name = f"{subject}_{session}_T1w.{suffix}"
            os.rename(os.path.join(anat_dest, file), os.path.join(anat_dest, new_name))


def convert_flair(
    subj_dir: str,
    subject: str,
    session: str,
    converter: str = DCM_CONVERTER_PATH,
) -> None:
    """Convert raw ANATOMY/FLAIR DICOM directory to BIDS anat FLAIR structure."""
    flair_src = os.path.join(subj_dir, "ANATOMY")
    if not os.path.exists(flair_src):
        print("No FLAIR files to process. Moving on.")
        return

    print("Starting conversion of FLAIR scans...")
    anat_dest = os.path.join(subj_dir, session, "anat")
    os.makedirs(anat_dest, exist_ok=True)
    existing_files = set(os.listdir(anat_dest))

    cmd = [converter, "-f", "%p_%s", "-p", "y", "-z", "y", "-o", anat_dest, flair_src]
    subprocess.run(cmd, check=False)

    for file in os.listdir(anat_dest):
        if file not in existing_files:
            suffix = get_suffix(file)
            new_name = f"{subject}_{session}_FLAIR.{suffix}"
            os.rename(os.path.join(anat_dest, file), os.path.join(anat_dest, new_name))


def convert_dti(
    subj_dir: str,
    subject: str,
    session: str,
    converter: str = DCM_CONVERTER_PATH,
) -> None:
    """Convert raw DTI DICOM directory to BIDS dwi structure."""
    dti_src = os.path.join(subj_dir, "DTI")
    if not os.path.exists(dti_src):
        print("No DTI files to process. Moving on.")
        return

    print("Starting conversion of DTI scans...")
    dwi_dest = os.path.join(subj_dir, session, "dwi")
    os.makedirs(dwi_dest, exist_ok=True)
    existing_files = set(os.listdir(dwi_dest))

    cmd = [converter, "-f", "%p_%s", "-p", "y", "-z", "y", "-o", dwi_dest, dti_src]
    subprocess.run(cmd, check=False)

    suffix_numbers: Dict[str, int] = defaultdict(int)
    for file in os.listdir(dwi_dest):
        suffix_numbers[file.split(".")[0].split("_")[-1]] += 1

    for file in os.listdir(dwi_dest):
        if file not in existing_files:
            suffix = get_suffix(file)
            old_name = file.split(".")[0]
            enum_key = old_name.split("_")[-1]
            if suffix_numbers[enum_key] == 4:
                if "ep2d_diff" not in file:
                    print(f"Not a DTI file ({file}). Skipping.")
                    continue
                direction = "pa" if "_PA_" in old_name else "ap"
                new_name = f"{subject}_{session}_dwi_{direction}.{suffix}"
                os.rename(os.path.join(dwi_dest, file), os.path.join(dwi_dest, new_name))
            else:
                os.remove(os.path.join(dwi_dest, file))


def convert_rest(
    subj_dir: str,
    subject: str,
    session: str,
    converter: str = DCM_CONVERTER_PATH,
) -> None:
    """Convert raw REST DICOM directory to BIDS func resting-state structure."""
    rest_src = os.path.join(subj_dir, "REST")
    if not os.path.exists(rest_src):
        print("No RS files to process. Moving on.")
        return

    print("Starting conversion of RS scans...")
    func_dest = os.path.join(subj_dir, session, "func")
    os.makedirs(func_dest, exist_ok=True)
    existing_files = set(os.listdir(func_dest))

    cmd = [converter, "-f", "%p_%s", "-p", "y", "-z", "y", "-o", func_dest, rest_src]
    subprocess.run(cmd, check=False)

    for file in os.listdir(func_dest):
        if file not in existing_files:
            if "CBU_REST" not in file:
                continue
            suffix = get_suffix(file)
            echo = get_echo(file)
            new_name = f"{subject}_{session}_task-rest_{echo}_bold.{suffix}"
            os.rename(os.path.join(func_dest, file), os.path.join(func_dest, new_name))


def convert_tim_runs(
    subj_dir: str,
    subject: str,
    session: str,
    runs: int = 5,
    converter: str = DCM_CONVERTER_PATH,
) -> None:
    """Convert raw TIM run DICOM folders to BIDS multi-echo functional files."""
    func_dest = os.path.join(subj_dir, session, "func")
    os.makedirs(func_dest, exist_ok=True)

    for tim_run in range(1, runs + 1):
        malformatted = os.path.join(subj_dir, f"TIM {tim_run}")
        tim_folder = os.path.join(subj_dir, f"TIM{tim_run}")
        if os.path.exists(malformatted):
            os.rename(malformatted, tim_folder)

        if not os.path.exists(tim_folder):
            print(f"Warning: No TIM scans of run {tim_run} to process. Moving on.")
            continue

        print(f"Starting conversion of TIM {tim_run} scans...")
        existing_files = set(os.listdir(func_dest))
        cmd = [converter, "-f", "%p_%s", "-p", "y", "-z", "y", "-o", func_dest, tim_folder]
        subprocess.run(cmd, check=False)

        for file in os.listdir(func_dest):
            if file not in existing_files:
                if "CBU_TIM" not in file:
                    continue
                suffix = get_suffix(file)
                echo = get_echo(file)
                new_name = f"{subject}_{session}_task-tim_run-{tim_run}_{echo}_bold.{suffix}"
                os.rename(os.path.join(func_dest, file), os.path.join(func_dest, new_name))


def process_tim_events_and_ratings(
    subj_dir: str,
    subject: str,
    session: str,
    runs: int = 5,
) -> None:
    """Process event onset CSVs and subjective pain rating files."""
    func_dest = os.path.join(subj_dir, session, "func")
    os.makedirs(func_dest, exist_ok=True)

    # Process onset files
    print("Preparing event_onset files...")
    for current_file in os.listdir(subj_dir):
        if current_file.startswith("TIM_event_onset"):
            match = re.search(r"block_(\d+)", current_file)
            if not match:
                continue
            run_number = int(match.group(1))
            file_path = os.path.join(subj_dir, current_file)
            df = pd.read_csv(file_path, delimiter="\t")
            if "Unnamed: 0" in df.columns:
                df.drop("Unnamed: 0", axis=1, inplace=True)
            df = df.round({"Time": 2, "Duration": 2})
            new_file_name = f"{subject}_{session}_task-tim_run-{run_number}_events.tsv"
            df.to_csv(os.path.join(func_dest, new_file_name), sep="\t", index=False)

    # Read pain rating files
    pain_ratings = None
    for current_file in os.listdir(subj_dir):
        if "Pain" in current_file and current_file.endswith(".csv"):
            file_path = os.path.join(subj_dir, current_file)
            df = pd.read_csv(file_path)
            if "Pain" in df.columns:
                pain_ratings = df["Pain"]

    # Generate timing files via era_to_timing
    for file in os.listdir(subj_dir):
        full_path = os.path.join(subj_dir, file)
        if file.endswith("_era_2s.txt"):
            era_to_timing.get_anticipation_scr_timing_file(
                era_path=full_path,
                events_path=func_dest,
                output_path=func_dest,
                blocks=runs,
            )
        elif file.endswith("_era_4s.txt"):
            era_to_timing.get_pain_scr_timing_file(
                era_path=full_path,
                events_path=func_dest,
                output_path=func_dest,
                blocks=runs,
                pain_ratings=pain_ratings,
            )
            era_to_timing.get_pain_rating_scr_timing_file(
                era_path=full_path,
                events_path=func_dest,
                output_path=func_dest,
                blocks=runs,
                pain_ratings=pain_ratings,
            )


def preprocess_subject_mri(
    subject: str,
    session: str = "ses-1",
    runs: int = 5,
    base_dir: str = ".",
    converter: str = DCM_CONVERTER_PATH,
) -> None:
    """Execute complete DICOM-to-BIDS conversion workflow for a TIM subject."""
    if not subject.startswith("sub-"):
        raise ValueError(f"Subject format invalid: {subject}. Expected sub-xx.")

    subj_dir = os.path.join(base_dir, subject)
    if not os.path.isdir(subj_dir):
        raise FileNotFoundError(f"Subject directory does not exist: {subj_dir}")

    session_dir = os.path.join(subj_dir, session)
    os.makedirs(session_dir, exist_ok=True)

    convert_fieldmap(subj_dir, subject, session, converter=converter)
    convert_t1(subj_dir, subject, session, converter=converter)
    convert_flair(subj_dir, subject, session, converter=converter)
    convert_dti(subj_dir, subject, session, converter=converter)
    convert_rest(subj_dir, subject, session, converter=converter)
    convert_tim_runs(subj_dir, subject, session, runs=runs, converter=converter)
    process_tim_events_and_ratings(subj_dir, subject, session, runs=runs)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for mri_file_preprocess."""
    parser = argparse.ArgumentParser(
        description="Convert scanner DICOM directories into BIDS structure for TIM paradigm."
    )
    parser.add_argument("subject", help="Subject ID, in the format of sub-xx.")
    parser.add_argument("--session", default="1", help="Session ID - 1 or 2 (default 1).")
    parser.add_argument("--runs", type=int, default=5, help="Number of TIM functional runs (default 5).")
    parser.add_argument("--era", default=None, help="Optional path to Ledalab ERA file.")
    parser.add_argument("--base_dir", default=".", help="Base directory containing subject folder.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for mri_file_preprocess."""
    args = parse_args(argv)
    try:
        ses_num = int(str(args.session).replace("ses-", ""))
        session_tag = f"ses-{ses_num}"
    except (ValueError, TypeError):
        print(f"Invalid session identifier: {args.session}. Please enter an integer or ses-N.", file=sys.stderr)
        return 1

    try:
        preprocess_subject_mri(
            subject=args.subject,
            session=session_tag,
            runs=args.runs,
            base_dir=args.base_dir,
        )
        print("MRI preprocessing complete.")
        return 0
    except Exception as exc:
        print(f"Error during MRI file preprocessing: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())