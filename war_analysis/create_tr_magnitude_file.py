import argparse
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("binned_tsv", required=True, help="Specify the path of the binned TSV file")
parser.add_argument("lag", type=int, help="Specify the amount of time to subtract from onset")
parser.add_argument("output", required=True, help="Specify the path of the output txt file")
args = parser.parse_args()

if args.binned_tsv:
    binned_tsv = args.binned_tsv
if args.lag:
    lag = args.lag
if args.output:
    output = args.output

TRs = 286 if lag == 28 else 300

df = pd.read_csv(binned_tsv, sep="\t", header=None)
df["Time"] = df["Time"] - lag

magnitudes = [0] * TRs
for _, row in df.iterrows():
    index = row["Time"] // 2
    magnitudes[index] = row["Amplitude"]

with open(output, "w") as f:
    for mag in magnitudes:
        f.write(f"{mag}\n")