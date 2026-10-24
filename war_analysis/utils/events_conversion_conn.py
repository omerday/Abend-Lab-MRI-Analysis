"""WAR log file to CONN/BIDS event format converter.

Converts presentation log files into BIDS-compliant event TSV files for the
CONN functional connectivity toolbox and AFNI first-level modeling.
Maps Biopac triggers to condition labels (Negative, Neutral, Positive, Rest, Block).
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Default lag adjustments (in seconds) per session, subject, and run
DEFAULT_LAGS: Dict[str, Dict[str, Dict[str, int]]] = {
    "ses-1": {
        "sub-AL18": {"run-1": 28, "run-2": 28},
        "sub-AL19": {"run-1": 28, "run-2": 28},
        "sub-AL20": {"run-1": 28, "run-2": 28},
        "sub-AL21": {"run-1": 28, "run-2": 28},
        "sub-AL22": {"run-1": 28, "run-2": 28},
        "sub-AL23": {"run-1": 28, "run-2": 28},
        "sub-AL24": {"run-1": 28, "run-2": 28},
        "sub-AL25": {"run-1": 28, "run-2": 28},
        "sub-AL26": {"run-1": 28, "run-2": 28},
        "sub-AL27": {"run-1": 28, "run-2": 28},
        "sub-AL28": {"run-1": 28, "run-2": 28},
        "sub-AL41": {"run-1": 0, "run-2": 0},
        "sub-AL48": {"run-1": 0, "run-2": 0},
        "sub-AL49": {"run-1": 0, "run-2": 0},
        "sub-AL50": {"run-1": 0, "run-2": 0},
        "sub-AL51": {"run-1": 0, "run-2": 0},
        "sub-AL52": {"run-1": 0, "run-2": 0},
        "sub-AL53": {"run-1": 0, "run-2": 0},
        "sub-AL55": {"run-1": 0, "run-2": 0},
        "sub-AL58": {"run-1": 0, "run-2": 0},
        "sub-AL59": {"run-1": 0, "run-2": 0},
        "sub-AL60": {"run-1": 0, "run-2": 0},
        "sub-AL61": {"run-1": 0, "run-2": 0},
        "sub-AL62": {"run-1": 0, "run-2": 0},
        "sub-AL65": {"run-1": 0, "run-2": 0},
        "sub-AL70": {"run-1": 0, "run-2": 0},
        "sub-AL71": {"run-1": 0, "run-2": 0},
        "sub-MD18": {"run-1": 28, "run-2": 28},
        "sub-MD21": {"run-1": 28, "run-2": 28},
        "sub-MD22": {"run-1": 28, "run-2": 28},
        "sub-MD23": {"run-1": 28, "run-2": 28},
        "sub-MD24": {"run-1": 28, "run-2": 28},
        "sub-MD25": {"run-1": 28, "run-2": 28},
        "sub-MD27": {"run-1": 28, "run-2": 28},
        "sub-MD28": {"run-1": 28, "run-2": 28},
        "sub-MD30": {"run-1": 0, "run-2": 0},
        "sub-MD35": {"run-1": 0, "run-2": 0},
        "sub-MD38": {"run-1": 0, "run-2": 17},
        "sub-MD41": {"run-1": 0, "run-2": 0},
        "sub-MD42": {"run-1": 0, "run-2": 36},
    },
    "ses-2": {
        "sub-MD18": {"run-1": 28, "run-2": 28},
        "sub-MD23": {"run-1": 28, "run-2": 28},
        "sub-MD24": {"run-1": 28, "run-2": 28},
        "sub-MD25": {"run-1": 0, "run-2": 21},
        "sub-MD27": {"run-1": 0, "run-2": 23},
        "sub-MD28": {"run-1": 0, "run-2": 19},
        "sub-MD30": {"run-1": 0, "run-2": 0},
    },
}

BLOCK_DEFINITIONS: Dict[int, str] = {
    31: "Negative_Block",
    51: "Neutral_Block",
    71: "Positive_Block",
}


def get_trial_type(biopac: int) -> Optional[str]:
    """Map Biopac event trigger code to descriptive condition label.

    Args:
        biopac: Numerical trigger code recorded by Biopac.

    Returns:
        Condition label string, or None if unmapped.
    """
    if 31 <= biopac <= 34:
        return f"Negative_Image_{biopac - 30}"
    if 51 <= biopac <= 54:
        return f"Neutral_Image_{biopac - 50}"
    if 71 <= biopac <= 74:
        return f"Positive_Image_{biopac - 70}"
    if biopac in [22, 24]:
        return "Rest"
    return None


def convert_war_log_file(
    file_path: Path,
    session: str = "ses-1",
    output_dir: Optional[Path] = None,
    lags: Optional[Dict[str, Dict[str, Dict[str, int]]]] = None,
) -> Path:
    """Convert an individual WAR log CSV file to BIDS events TSV format.

    Args:
        file_path: Path to raw WAR log CSV file.
        session: Session identifier string (e.g. 'ses-1').
        output_dir: Destination directory. If None, checks ./scans/<subject>/<session>/func.
        lags: Dictionary mapping sessions and subjects to run lag values.

    Returns:
        Path to generated BIDS events TSV file.

    Raises:
        FileNotFoundError: If input file_path does not exist.
        ValueError: If file name cannot be parsed for subject and run.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"WAR log file not found: {file_path}")

    parts = file_path.stem.split("_")
    # Expected pattern: ..._<subject>_..._<run>_...
    if len(parts) < 6:
        raise ValueError(
            f"Filename {file_path.name} cannot be parsed into subject and run (expected >= 6 tokens)."
        )

    # Sub-string after prefix e.g. AL18 -> sub-AL18
    raw_sub = parts[3]
    subject = f"sub-{raw_sub[2:]}" if raw_sub.startswith("sub") else f"sub-{raw_sub}"
    run = f"run-{parts[5]}"

    df = pd.read_csv(file_path)
    df["trial_type"] = df["Biopac"].apply(get_trial_type)
    df = df.dropna(subset=["trial_type"])

    active_lags = lags if lags is not None else DEFAULT_LAGS
    subject_lag = active_lags.get(session, {}).get(subject, {}).get(run, 0)
    df["onset"] = df["Time"] - subject_lag

    df = df[df["onset"] >= 0]
    df["onset"] = df["onset"].round(2)

    df = df.rename(columns={"Duration": "duration"})
    df["duration"] = df["duration"].round(2)

    new_block_rows: List[pd.DataFrame] = []
    for biopac_trigger, block_name in BLOCK_DEFINITIONS.items():
        block_instances = df[df["Biopac"] == biopac_trigger].copy()
        if not block_instances.empty:
            block_instances["trial_type"] = block_name
            block_instances["duration"] = 22
            new_block_rows.append(block_instances)

    if new_block_rows:
        df = pd.concat([df] + new_block_rows, ignore_index=True)

    df = df[["onset", "duration", "trial_type"]].sort_values(by="onset")

    output_filename = f"{subject}_{session}_task-war_{run}_events.tsv"
    if output_dir is not None:
        dest_dir = output_dir
    else:
        scans_func = Path(f"./scans/{subject}/{session}/func")
        dest_dir = scans_func if scans_func.is_dir() else Path(".")

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_file = dest_dir / output_filename
    df.to_csv(out_file, sep="\t", index=False)
    print(f"Saved event file to: {out_file}")
    return out_file


def convert_all_war_logs(
    base_dir: Path = Path("./log_files_raw"),
    session: str = "ses-1",
    output_dir: Optional[Path] = None,
) -> List[Path]:
    """Scan base_dir and convert all matching WAR log files.

    Args:
        base_dir: Root directory containing raw log files.
        session: Session identifier string.
        output_dir: Optional destination directory for output TSVs.

    Returns:
        List of generated event file paths.
    """
    pattern = "*WAR_LogFile*.csv"
    matching_files = list(base_dir.rglob(pattern)) if base_dir.is_dir() else []
    converted: List[Path] = []

    for file_path in matching_files:
        try:
            out_path = convert_war_log_file(file_path, session=session, output_dir=output_dir)
            converted.append(out_path)
        except Exception as exc:
            print(f"Failed to convert {file_path}: {exc}", file=sys.stderr)

    return converted


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for events_conversion_conn."""
    parser = argparse.ArgumentParser(
        description="Convert WAR log files into CONN-compliant BIDS events TSV files."
    )
    parser.add_argument(
        "--input_dir",
        default="./log_files_raw",
        help="Directory containing raw WAR log CSV files (searched recursively).",
    )
    parser.add_argument(
        "--session",
        default="ses-1",
        help="Session identifier (default 'ses-1').",
    )
    parser.add_argument(
        "--output_dir",
        default=None,
        help="Optional destination directory for converted event TSV files.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for events_conversion_conn."""
    args = parse_args(argv)
    in_path = Path(args.input_dir)
    out_path = Path(args.output_dir) if args.output_dir else None

    if in_path.is_file():
        convert_war_log_file(in_path, session=args.session, output_dir=out_path)
        return 0

    if not in_path.is_dir():
        print(f"Input directory not found: {in_path}", file=sys.stderr)
        return 1

    converted = convert_all_war_logs(
        base_dir=in_path,
        session=args.session,
        output_dir=out_path,
    )
    print(f"Successfully converted {len(converted)} log file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())