"""Ledalab ERA to AFNI 1D timing converter for the WAR pipeline.

Extracts Skin Conductance Response (SCR) metrics from Ledalab Event-Related
Analysis (ERA) exports and aligns them with BIDS event onsets for GLM amplitude
modulation in AFNI (image-level and 11-bin block expansions).
"""

import argparse
import os
import sys
from typing import List, Optional

import numpy as np
import pandas as pd

# Event codes for image presentations across valence conditions (neg: 31-34, neu: 51-54, pos: 71-74)
IMAGE_ONSET_EVENTS: List[int] = [
    31, 32, 33, 34,
    51, 52, 53, 54,
    71, 72, 73, 74,
]

# Event codes marking block starts (neg: 31, neu: 51, pos: 71)
BLOCK_START_EVENTS: List[int] = [31, 51, 71]


def process_image_era(
    era_path: str,
    events_path: str = "./",
    output_path: str = "./",
    blocks: int = 2,
) -> None:
    """Process image-level ERA SCR amplitudes for the WAR paradigm.

    Calculates delta amplitude (Global.Mean - CDA.Tonic) rounded to 5 decimal places
    for each image event and aligns it with corresponding BIDS onset timings.

    Args:
        era_path: Path to Ledalab ERA file.
        events_path: Directory containing task-war_run-*_events.tsv files.
        output_path: Destination directory for generated timing files.
        blocks: Number of runs/blocks (default 2).

    Raises:
        ValueError: If era_path is empty.
        FileNotFoundError: If era_path or event TSV cannot be found.
    """
    if not era_path:
        raise ValueError("ERA path empty.")
    if not os.path.exists(era_path):
        raise FileNotFoundError(f"ERA path is invalid: {era_path}")

    os.makedirs(output_path, exist_ok=True)
    era_df = pd.read_csv(era_path, sep=r"\s+")
    era_df = era_df[era_df["Event.Name"].isin(IMAGE_ONSET_EVENTS)]

    for i in range(1, blocks + 1):
        target_suffix = f"task-war_run-{i}_events.tsv"
        file_name = next(
            (f for f in os.listdir(events_path) if f.endswith(target_suffix)),
            "",
        )
        if not file_name:
            raise FileNotFoundError(
                f"Event file for round {i} ({target_suffix}) not found in {events_path}."
            )

        events_file_full = os.path.join(events_path, file_name)
        timing_df = pd.read_csv(events_file_full, sep="\t")

        df_len = len(era_df)
        block_df = era_df.iloc[
            df_len - (4 * 3 * 3 * (blocks - i + 1)):df_len - (4 * 3 * 3 * (blocks - i))
        ]

        events = timing_df[timing_df["Biopac"].isin(IMAGE_ONSET_EVENTS)]["Biopac"]
        timings = timing_df[timing_df["Biopac"].isin(IMAGE_ONSET_EVENTS)]["Time"]
        global_means = block_df[block_df["Event.Name"].isin(IMAGE_ONSET_EVENTS)]["Global.Mean"]
        cda_tonic = block_df[block_df["Event.Name"].isin(IMAGE_ONSET_EVENTS)]["CDA.Tonic"]
        amp = np.round(global_means - cda_tonic, 5)

        aggregated_df = pd.DataFrame({
            "Event": events.values,
            "Time": timings.values,
            "Amplitude": amp.values,
        }, columns=["Event", "Time", "Amplitude"])

        new_timing_name = os.path.join(output_path, f"image_scr_run-{i}.txt")
        aggregated_df.to_csv(new_timing_name, sep="\t", header=False, index=False)


def process_binned_era(
    era_path: str,
    events_path: str = "./",
    output_path: str = "./",
    blocks: int = 2,
) -> None:
    """Process block start ERA records into 11 TR bins per block (2.0s spacing).

    Args:
        era_path: Path to Ledalab ERA file.
        events_path: Directory containing task-war_run-*_events.tsv files.
        output_path: Destination directory for generated timing files.
        blocks: Number of runs/blocks (default 2).

    Raises:
        ValueError: If era_path is empty.
        FileNotFoundError: If era_path or event TSV cannot be found.
    """
    if not era_path:
        raise ValueError("ERA path empty.")
    if not os.path.exists(era_path):
        raise FileNotFoundError(f"ERA path is invalid: {era_path}")

    os.makedirs(output_path, exist_ok=True)
    era_df = pd.read_csv(era_path, sep=r"\s+")
    era_df = era_df[era_df["Event.Name"].isin(BLOCK_START_EVENTS)]

    for i in range(1, blocks + 1):
        target_suffix = f"task-war_run-{i}_events.tsv"
        file_name = next(
            (f for f in os.listdir(events_path) if f.endswith(target_suffix)),
            "",
        )
        if not file_name:
            raise FileNotFoundError(
                f"Event file for round {i} ({target_suffix}) not found in {events_path}."
            )

        events_file_full = os.path.join(events_path, file_name)
        timing_df = pd.read_csv(events_file_full, sep="\t")

        df_len = len(era_df)
        block_df = era_df.iloc[
            df_len - (3 * 11 * 3 * (blocks - i + 1)):df_len - (3 * 11 * 3 * (blocks - i))
        ]

        records_list: List[dict] = []

        for event in BLOCK_START_EVENTS:
            timings: List[float] = []
            for time in timing_df[timing_df["Biopac"] == event]["Time"]:
                for j in range(11):
                    timings.append(round(time + j * 2, 2))

            global_means = block_df[block_df["Event.Name"] == event]["Global.Mean"]
            cda_tonic = block_df[block_df["Event.Name"] == event]["CDA.Tonic"]
            amp = np.round(global_means - cda_tonic, 5)

            for t_val, a_val in zip(timings, amp):
                records_list.append({
                    "Event": event,
                    "Time": t_val,
                    "Amplitude": a_val,
                })

        if records_list:
            aggregated_df = pd.DataFrame(records_list, columns=["Event", "Time", "Amplitude"])
        else:
            aggregated_df = pd.DataFrame(columns=["Event", "Time", "Amplitude"])

        new_timing_name = os.path.join(output_path, f"binned_scr_run-{i}.txt")
        aggregated_df.to_csv(new_timing_name, sep="\t", header=True, index=False)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for process_era_files."""
    parser = argparse.ArgumentParser(
        description="Process Ledalab ERA files for WAR experiment into AFNI 1D timing files."
    )
    parser.add_argument("--era_path", required=True, help="Path to Ledalab ERA file.")
    parser.add_argument("--events_path", default="./", help="Directory containing events TSV files.")
    parser.add_argument("--output_path", default="./", help="Output directory for timing files.")
    parser.add_argument("--blocks", type=int, default=2, help="Number of experimental blocks/runs.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for process_era_files."""
    args = parse_args(argv)
    try:
        process_image_era(
            era_path=args.era_path,
            events_path=args.events_path,
            output_path=args.output_path,
            blocks=args.blocks,
        )
        process_binned_era(
            era_path=args.era_path,
            events_path=args.events_path,
            output_path=args.output_path,
            blocks=args.blocks,
        )
        return 0
    except Exception as exc:
        print(f"Error processing WAR ERA files: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
