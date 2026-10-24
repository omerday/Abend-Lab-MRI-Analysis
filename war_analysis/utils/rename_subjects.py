"""Subject ID prefixing utility for WAR MRI dataset renumbering.

Renames subject folders and internal filenames from sub-xx to sub-<prefix>xx
(e.g., sub-18 to sub-118 with prefix '1'), updating session subdirectories
(anat, func, fmap, dwi) and purging obsolete anat_warped trees.
"""

import argparse
import os
import shutil
import sys
from typing import List, Optional

VALID_SUBDIRS: List[str] = ["anat", "func", "fmap", "dwi", "anat_warped"]


def rename_subject_directory(
    subject: str,
    prefix: str,
    base_dir: str = ".",
) -> str:
    """Rename subject directory and all matching files within its sessions.

    Args:
        subject: Original subject ID (e.g. 'sub-18').
        prefix: Prefix to prepend before the numerical ID (e.g. '1' -> 'sub-118').
        base_dir: Base directory containing subject folders.

    Returns:
        The new subject ID string.

    Raises:
        ValueError: If subject or prefix are invalid or not starting with 'sub-'.
        FileNotFoundError: If the subject directory does not exist in base_dir.
    """
    if not subject:
        raise ValueError("Subject identifier cannot be empty.")
    if not subject.startswith("sub-"):
        raise ValueError(f"Invalid subject format: {subject}. Expected prefix 'sub-'.")
    if not prefix:
        raise ValueError("Prefix cannot be empty.")

    old_subject_path = os.path.join(base_dir, subject)
    if not os.path.isdir(old_subject_path):
        raise FileNotFoundError(f"Subject folder not found: {old_subject_path}")

    old_id = subject.split("-")[-1]
    new_subject = f"sub-{prefix}{old_id}"
    new_subject_path = os.path.join(base_dir, new_subject)

    print(f"Renaming directory: {old_subject_path} -> {new_subject_path}")
    os.rename(old_subject_path, new_subject_path)

    sessions = [
        item for item in os.listdir(new_subject_path)
        if "ses-" in item and os.path.isdir(os.path.join(new_subject_path, item))
    ]

    for session in sessions:
        session_path = os.path.join(new_subject_path, session)
        print(f"Processing session {session} in {session_path}")

        for folder in VALID_SUBDIRS:
            folder_path = os.path.join(session_path, folder)
            if not os.path.isdir(folder_path):
                continue

            if folder == "anat_warped":
                try:
                    shutil.rmtree(folder_path)
                    print(f"Purged obsolete warped directory: {folder_path}")
                    continue
                except OSError as exc:
                    print(f"Could not remove {folder_path}: {exc}", file=sys.stderr)
                    continue

            for file in os.listdir(folder_path):
                if subject in file:
                    new_file_name = file.replace(subject, new_subject)
                    src = os.path.join(folder_path, file)
                    dst = os.path.join(folder_path, new_file_name)
                    print(f"Renaming {file} -> {new_file_name}")
                    os.rename(src, dst)

    return new_subject


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for rename_subjects."""
    parser = argparse.ArgumentParser(
        description="Rename subject directory and files with an ID prefix (e.g. sub-18 -> sub-118)."
    )
    parser.add_argument("subject", help="Subject ID, in the format of sub-xx")
    parser.add_argument("--prefix", required=True, help="Prefix to add before ID (e.g. '1' for sub-1xx)")
    parser.add_argument(
        "--base_dir",
        default=".",
        help="Base directory containing subject folders (default: current directory).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for rename_subjects."""
    args = parse_args(argv)
    try:
        new_name = rename_subject_directory(
            subject=args.subject,
            prefix=args.prefix,
            base_dir=args.base_dir,
        )
        print(f"Successfully renamed {args.subject} to {new_name}.")
        return 0
    except Exception as exc:
        print(f"Error renaming subject: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
