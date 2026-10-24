"""Ledalab ERA to AFNI 1D timing converter for the TIM pipeline.

Extracts Skin Conductance Response (SCR) metrics from Ledalab Event-Related
Analysis (ERA) exports and aligns them with BIDS event onsets for GLM amplitude
modulation in AFNI.
"""

import argparse
import os
import sys
from typing import List, Optional

import numpy as np
import pandas as pd

# Event codes for anticipation conditions across pain intensities (low: 21-25, med: 41-45, high: 81-85)
VALID_ANTICIPATION_EVENTS: List[int] = [
    21, 22, 23, 24, 25,
    41, 42, 43, 44, 45,
    81, 82, 83, 84, 85,
]

# Event codes for pain stimulation (low: 26, med: 46, high: 86)
VALID_PAIN_EVENTS: List[int] = [26, 46, 86]

# Event codes for post-pain rating window (low: 27, med: 47, high: 87)
VALID_PAIN_RATING_EVENTS: List[int] = [27, 47, 87]


def get_anticipation_scr_timing_file(
    era_path: str,
    events_path: str = "./",
    output_path: str = "./",
    blocks: int = 5,
) -> None:
    """Generate anticipation SCR amplitude modulation timing files across runs.

    Calculates mean SCR amplitude difference (Global.Mean - CDA.Tonic) for
    each anticipation event code and pairs it with the corresponding BIDS onset.

    Args:
        era_path: Path to the Ledalab ERA TSV export file.
        events_path: Directory containing BIDS task-tim_run-*_events.tsv files.
        output_path: Output directory for generated timing text files.
        blocks: Number of experimental runs/blocks (default 5).

    Raises:
        ValueError: If era_path is empty.
        FileNotFoundError: If era_path or an event TSV file does not exist.
    """
    if not era_path:
        raise ValueError("ERA path empty.")
    if not os.path.exists(era_path):
        raise FileNotFoundError(f"ERA path is invalid: {era_path}")

    os.makedirs(output_path, exist_ok=True)
    era_df = pd.read_csv(era_path, sep="\t")
    era_df = era_df[era_df["Event.Name"].isin(VALID_ANTICIPATION_EVENTS)]

    for i in range(1, blocks + 1):
        target_suffix = f"task-tim_run-{i}_events.tsv"
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

        block_df = era_df.iloc[(30 * (i - 1)):(30 * i), :]
        records_list: List[dict] = []

        for event in VALID_ANTICIPATION_EVENTS:
            timings = timing_df[timing_df["condition"] == event]["onset"]
            global_means = block_df[block_df["Event.Name"] == event]["Global.Mean"]
            cda_tonic = block_df[block_df["Event.Name"] == event]["CDA.Tonic"]

            diff = global_means - cda_tonic
            amp = float(np.round(np.average(diff), 2)) if len(diff) > 0 else 0.0
            if np.isnan(amp):
                amp = 0.0

            for time in timings:
                records_list.append({
                    "Event": event,
                    "Time": time,
                    "Amplitude": amp,
                })

        if records_list:
            aggregated_df = pd.DataFrame(records_list, columns=["Event", "Time", "Amplitude"])
        else:
            aggregated_df = pd.DataFrame(columns=["Event", "Time", "Amplitude"])

        new_timing_name = os.path.join(output_path, f"anticipation_scr_amplitude_run-{i}.txt")
        aggregated_df.to_csv(new_timing_name, sep="\t", header=False, index=False)


def get_pain_rating_scr_timing_file(
    era_path: str,
    events_path: str = "./",
    output_path: str = "./",
    blocks: int = 5,
    pain_ratings: Optional[pd.DataFrame] = None,
) -> None:
    """Generate post-pain rating SCR amplitude timing files.

    Args:
        era_path: Path to the Ledalab ERA TSV export file.
        events_path: Directory containing BIDS task-tim_run-*_events.tsv files.
        output_path: Output directory for generated timing text files.
        blocks: Number of experimental runs/blocks (default 5).
        pain_ratings: Optional DataFrame containing subjective pain rating values.

    Raises:
        ValueError: If era_path is empty.
        FileNotFoundError: If era_path or an event TSV file does not exist.
    """
    if not era_path:
        raise ValueError("ERA path empty.")
    if not os.path.exists(era_path):
        raise FileNotFoundError(f"ERA path is invalid: {era_path}")

    os.makedirs(output_path, exist_ok=True)
    era_df = pd.read_csv(era_path, sep="\t")
    era_df = era_df[era_df["Event.Name"].isin(VALID_PAIN_RATING_EVENTS)]
    if len(era_df) > blocks * 6:
        era_df = era_df.iloc[len(era_df) - (blocks * 6):, :]

    if pain_ratings is not None and len(pain_ratings) > blocks * 6:
        pain_ratings = pain_ratings.iloc[len(pain_ratings) - (blocks * 6):]

    for i in range(1, blocks + 1):
        target_suffix = f"task-tim_run-{i}_events.tsv"
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

        block_df = era_df.iloc[(6 * (i - 1)):(6 * i), :]
        if pain_ratings is not None:
            pain_ratings_block = pain_ratings.iloc[(i - 1) * 6:i * 6].values
        else:
            pain_ratings_block = [0] * 6

        events = timing_df[timing_df["condition"].isin(VALID_PAIN_RATING_EVENTS)]["condition"]
        timings = timing_df[timing_df["condition"].isin(VALID_PAIN_RATING_EVENTS)]["onset"]
        global_means = block_df[block_df["Event.Name"].isin(VALID_PAIN_RATING_EVENTS)]["Global.Mean"]
        amp = np.round(global_means, 2)

        aggregated_df = pd.DataFrame({
            "Event": events.values,
            "Time": timings.values,
            "Amplitude": amp.values,
            "Rating": pain_ratings_block,
        }, columns=["Event", "Time", "Amplitude", "Rating"])

        new_timing_name = os.path.join(output_path, f"post_pain_scr_amplitude_run-{i}.txt")
        aggregated_df.to_csv(new_timing_name, sep="\t", header=False, index=False)


def get_pain_scr_timing_file(
    era_path: str,
    events_path: str = "./",
    output_path: str = "./",
    blocks: int = 5,
    pain_ratings: Optional[pd.DataFrame] = None,
) -> None:
    """Generate pain stimulation SCR amplitude timing files.

    Args:
        era_path: Path to the Ledalab ERA TSV export file.
        events_path: Directory containing BIDS task-tim_run-*_events.tsv files.
        output_path: Output directory for generated timing text files.
        blocks: Number of experimental runs/blocks (default 5).
        pain_ratings: Optional DataFrame containing subjective pain rating values.

    Raises:
        ValueError: If era_path is empty.
        FileNotFoundError: If era_path or an event TSV file does not exist.
    """
    if not era_path:
        raise ValueError("ERA path empty.")
    if not os.path.exists(era_path):
        raise FileNotFoundError(f"ERA path is invalid: {era_path}")

    os.makedirs(output_path, exist_ok=True)
    era_df = pd.read_csv(era_path, sep="\t")
    era_df = era_df[era_df["Event.Name"].isin(VALID_PAIN_EVENTS)]
    if len(era_df) > blocks * 6:
        era_df = era_df.iloc[len(era_df) - (blocks * 6):, :]

    if pain_ratings is not None and len(pain_ratings) > blocks * 6:
        pain_ratings = pain_ratings.iloc[len(pain_ratings) - (blocks * 6):]

    for i in range(1, blocks + 1):
        target_suffix = f"task-tim_run-{i}_events.tsv"
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

        block_df = era_df.iloc[(6 * (i - 1)):(6 * i), :]
        if pain_ratings is not None:
            pain_ratings_block = pain_ratings.iloc[(i - 1) * 6:i * 6].values
        else:
            pain_ratings_block = [0] * 6

        events = timing_df[timing_df["condition"].isin(VALID_PAIN_EVENTS)]["condition"]
        timings = timing_df[timing_df["condition"].isin(VALID_PAIN_EVENTS)]["onset"]
        global_means = block_df[block_df["Event.Name"].isin(VALID_PAIN_EVENTS)]["Global.Mean"]
        amp = np.round(global_means, 2)

        aggregated_df = pd.DataFrame({
            "Event": events.values,
            "Time": timings.values,
            "Amplitude": amp.values,
            "Rating": pain_ratings_block,
        }, columns=["Event", "Time", "Amplitude", "Rating"])

        new_timing_name = os.path.join(output_path, f"pain_scr_amplitude_run-{i}.txt")
        aggregated_df.to_csv(new_timing_name, sep="\t", header=False, index=False)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for era_to_timing converter."""
    parser = argparse.ArgumentParser(
        description="Convert Ledalab ERA TSV files into AFNI 1D timing files for TIM paradigm."
    )
    parser.add_argument("--era_path", required=True, help="Path to Ledalab ERA TSV file.")
    parser.add_argument("--events_path", default="./", help="Directory containing events TSV files.")
    parser.add_argument("--output_path", default="./", help="Output directory for timing files.")
    parser.add_argument("--blocks", type=int, default=5, help="Number of experimental blocks/runs.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for era_to_timing."""
    args = parse_args(argv)
    try:
        get_anticipation_scr_timing_file(
            era_path=args.era_path,
            events_path=args.events_path,
            output_path=args.output_path,
            blocks=args.blocks,
        )
        get_pain_scr_timing_file(
            era_path=args.era_path,
            events_path=args.events_path,
            output_path=args.output_path,
            blocks=args.blocks,
        )
        get_pain_rating_scr_timing_file(
            era_path=args.era_path,
            events_path=args.events_path,
            output_path=args.output_path,
            blocks=args.blocks,
        )
        return 0
    except Exception as exc:
        print(f"Error converting ERA files: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())