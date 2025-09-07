import os
import pandas as pd
import numpy as np

VALID_ANTICIPATION_EVENTS = [21, 22, 23, 24, 25,
                41, 42, 43, 44, 45,
                81, 82, 83, 84, 85]

VALID_PAIN_EVENTS = [26, 46, 86]

def get_anticipation_scr_timing_file(era_path: str, events_path="./", output_path="./", blocks=5):
    if not era_path:
        print("ERA path empty. Quitting")
        quit()
    print(f"Path received - {era_path}")
    if not os.path.exists(era_path):
        print("ERA path is invalid. Quitting.")
        quit()

    print("Extracting ERA to DataFrame...")
    era_df = pd.read_csv(era_path, sep="\t")
    era_df = era_df[era_df["Event.Name"].isin(VALID_ANTICIPATION_EVENTS)]
    print("Done.")

    for i in range(1, blocks + 1):
        print(f"Starting to process block {i}")
        file_name = ""
        for file in os.listdir(events_path):
            if file.endswith(f"task-tim_run-{i}_events.tsv"):
                file_name = file
        if not file_name:
            print(f"Event file for round {i} not found in {events_path}. Quitting.")
            quit()
        print(f"Found file {file_name}. Etracting to DataFrame...")
        timing_df = pd.read_csv((events_path + "/" + file_name).replace('//', '/'), sep="\t")
        print("Done.")

        aggregated_df = pd.DataFrame(columns=['Event', 'Time', 'Amplitude'])
        block_df = era_df.iloc[(30 * (i - 1)) : (30 * i),:]

        for event in VALID_ANTICIPATION_EVENTS:
            print(f"Processing event {event}...")
            timings = timing_df[timing_df["condition"] == event]["onset"]
            global_means = block_df[block_df["Event.Name"] == event]["Global.Mean"]
            cda_tonic = block_df[block_df["Event.Name"] == event]["CDA.Tonic"]
            amp = np.round(np.average(global_means - cda_tonic), 2)
            if amp in [np.nan, np.NaN, np.NAN]:
                print(f"Warning! NaN value found!")

            new_records = [{"Event": event,
                            "Time": time,
                            "Amplitude": amp} for time in timings]
            
            print(f"Adding new records to aggregated DF...")
            aggregated_df = pd.concat([aggregated_df, pd.DataFrame(new_records)])

        new_timing_name = f"{output_path}/anticipation_scr_amplitude_run-{i}.txt".replace('//','/')
        aggregated_df.to_csv(new_timing_name, sep="\t", header=False, index=False)

def get_pain_scr_timing_file(era_path: str, events_path="./", output_path="./", blocks=5, pain_ratings=None):
    if not era_path:
        print("ERA path empty. Quitting")
        quit()
    print(f"Path received - {era_path}")
    if not os.path.exists(era_path):
        print("ERA path is invalid. Quitting.")
        quit()

    print("Extracting ERA to DataFrame...")
    era_df = pd.read_csv(era_path, sep="\t")
    era_df = era_df[era_df["Event.Name"].isin(VALID_PAIN_EVENTS)]
    if len(era_df) != blocks * 6:
        print(f"Warning! Expected {blocks * 6} pain events, but found {len(era_df)}")
    era_df = era_df.iloc[len(era_df) - (blocks * 6): , :]
    print("Done.")

    print("Extracting pain ratings...")
    if pain_ratings is not None and len(pain_ratings) != blocks * 6:
        print(f"Warning! Expected {blocks * 6} pain ratings, but found {len(pain_ratings)}")
        pain_ratings = pain_ratings.iloc[len(pain_ratings) - (blocks * 6): ]
    print(pain_ratings)
    print("Done.")

    for i in range(1, blocks + 1):
        print(f"Starting to process block {i}")
        file_name = ""
        for file in os.listdir(events_path):
            if file.endswith(f"task-tim_run-{i}_events.tsv"):
                file_name = file
        if not file_name:
            print(f"Event file for round {i} not found in {events_path}. Quitting.")
            quit()
        print(f"Found file {file_name}. Extracting to DataFrame...")
        timing_df = pd.read_csv((events_path + "/" + file_name).replace('//', '/'), sep="\t")
        print("Done.")

        block_df = era_df.iloc[(6 * (i - 1)) : (6 * i),:]
        pain_ratings_block = pain_ratings.iloc[(i - 1) * 6 : i * 6].values if pain_ratings is not None else [0] * 6

        aggregated_df = pd.DataFrame(columns=['Event', 'Time', 'Amplitude', 'Rating'])
        events = timing_df[timing_df["condition"].isin(VALID_PAIN_EVENTS)]["condition"]
        print(events)
        timings = timing_df[timing_df["condition"].isin(VALID_PAIN_EVENTS)]["onset"]
        print(timings)
        global_means = block_df[block_df["Event.Name"].isin(VALID_PAIN_EVENTS)]["Global.Mean"]
        cda_tonic = block_df[block_df["Event.Name"].isin(VALID_PAIN_EVENTS)]["CDA.Tonic"]
        amp = np.round(global_means - cda_tonic, 2)
        print(amp)

        new_records = {"Event": events.values,
                        "Time": timings.values,
                        "Amplitude": amp.values,
                        "Rating": pain_ratings_block}
        print(f"Adding new records to aggregated DF...")
        aggregated_df = pd.concat([aggregated_df, pd.DataFrame(new_records)])
            
        new_timing_name = f"{output_path}/pain_scr_amplitude_run-{i}.txt".replace('//','/')
        aggregated_df.to_csv(new_timing_name, sep="\t", header=False, index=False)