import pandas as pd
from pathlib import Path
import os

lags = {
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
    }
}

for ses in ["ses-1"]:

    base_path = Path(f"./log_files_raw/ayelet")
    file_pattern = "*WAR_LogFile*.csv"

    matching_files = list(base_path.rglob(file_pattern))

    for file_path in matching_files:
        file_name_split = file_path.name.split("_")
        subject = f"sub-{file_name_split[3][2:]}"
        run = f"run-{file_name_split[5]}"

        df = pd.read_csv(file_path)

        # Define function to determine trial_type based on Biopac code
        def get_trial_type(biopac):
            if 31 <= biopac <= 34:
                return f"Negative_Image_{biopac - 30}"
            elif 51 <= biopac <= 54:
                return f"Neutral_Image_{biopac - 50}"
            elif 71 <= biopac <= 74:
                return f"Positive_Image_{biopac - 70}"
            elif biopac in [22, 24]:
                return "Rest"
            else:
                return None

        # Apply mapping and filter out unmapped rows
        df['trial_type'] = df['Biopac'].apply(get_trial_type)
        df = df.dropna(subset=['trial_type'])

        # Adjust onset based on subject lag
        # Default to 0 if subject not in lag dictionary
        subject_lag = lags[ses].get(subject, {}).get(run, 0)
        df['onset'] = df['Time'] - subject_lag

        # Filter out onsets below 0 and round to 2 decimal points
        df = df[df['onset'] >= 0]
        df['onset'] = df['onset'].round(2)

        # Rename Duration column and round duration
        df = df.rename(columns={'Duration': 'duration'})
        df['duration'] = df['duration'].round(2)

        # Create duplicate entries for Block events
        block_definitions = {
            31: 'Negative_Block',
            51: 'Neutral_Block',
            71: 'Positive_Block'
        }

        new_block_rows = []
        for biopac_trigger, block_name in block_definitions.items():
            # Select rows matching the trigger
            block_instances = df[df['Biopac'] == biopac_trigger].copy()
            if not block_instances.empty:
                block_instances['trial_type'] = block_name
                block_instances['duration'] = 22
                new_block_rows.append(block_instances)

        # Append block rows if any exist
        if new_block_rows:
            df = pd.concat([df] + new_block_rows, ignore_index=True)

        # Select final columns and sort by onset
        df = df[['onset', 'duration', 'trial_type']].sort_values(by='onset')

        # Save to TSV
        output_filename = f"{subject}_{ses}_task-war_{run}_events.tsv"
        if os.path.exists(f"./scans/{subject}/{ses}/func"):
            output_filename = f"./scans/{subject}/{ses}/func/{output_filename}"
        print("Saving to:", output_filename)
        df.to_csv(output_filename, sep='\t', index=False)
        