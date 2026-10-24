"""AFNI 1D TR magnitude file generator from binned SCR events.

Maps binned Skin Conductance Response events into repetition time (TR = 2.0s) bins,
producing a single-column 1D file suitable for 3dDeconvolve amplitude modulation
with -stim_times_AM2 or file-based regressors.
"""

import argparse
import os
import sys
from typing import List, Optional

import pandas as pd


def compute_tr_magnitudes(binned_tsv: str, lag: int = 0) -> List[float]:
    """Compute TR magnitude array from binned TSV events.

    For lag == 28, scan duration is modeled as 286 TRs (after discarding initial lag).
    Otherwise, scan duration defaults to 300 TRs.

    Args:
        binned_tsv: Path to TSV file containing 'Time' and 'Amplitude' columns.
        lag: Amount of lead time in seconds to subtract from onset timings (default 0).

    Returns:
        List of float amplitude values indexed by TR slot (slot width = 2.0s).

    Raises:
        FileNotFoundError: If binned_tsv does not exist.
        ValueError: If required columns ('Time', 'Amplitude') are missing.
    """
    if not os.path.isfile(binned_tsv):
        raise FileNotFoundError(f"Binned TSV file not found: {binned_tsv}")

    trs = 286 if lag == 28 else 300
    df = pd.read_csv(binned_tsv, sep="\t")

    try:
        df["Time"] = df["Time"] - lag
    except (KeyError, TypeError) as err:
        raise ValueError(
            f"Expected 'Time' column in {binned_tsv}"
        ) from err

    magnitudes = [0.0] * trs

    for _, row in df.iterrows():
        time_val = row["Time"]
        if time_val > 0:
            index = int(time_val // 2)
            if 0 <= index < trs:
                magnitudes[index] = row["Amplitude"]

    return magnitudes


def create_tr_magnitude_file(binned_tsv: str, output_path: str, lag: int = 0) -> None:
    """Generate and write 1D TR magnitude file from binned TSV events.

    Args:
        binned_tsv: Path to source TSV file.
        output_path: Destination path for output 1D file.
        lag: Lead time in seconds to subtract from onsets.
    """
    magnitudes = compute_tr_magnitudes(binned_tsv, lag=lag)
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f_out:
        for mag in magnitudes:
            f_out.write(f"{mag}\n")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for create_tr_magnitude_file."""
    parser = argparse.ArgumentParser(
        description="Convert binned SCR event TSV into an AFNI 1D TR magnitude vector."
    )
    parser.add_argument(
        "--binned_tsv",
        required=True,
        help="Specify the path of the binned TSV file",
    )
    parser.add_argument(
        "--lag",
        type=int,
        default=0,
        help="Specify the amount of time in seconds to subtract from onset",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Specify the path of the output 1D file",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for create_tr_magnitude_file."""
    args = parse_args(argv)
    try:
        create_tr_magnitude_file(
            binned_tsv=args.binned_tsv,
            output_path=args.output,
            lag=args.lag or 0,
        )
        return 0
    except Exception as exc:
        print(f"Error creating TR magnitude file: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())