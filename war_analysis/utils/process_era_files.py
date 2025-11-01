import os
import pandas as pd
import numpy as np

IMAGE_ONSET_EVENTS = [31, 32, 33, 34,
                      51, 52, 53, 54,
                      71, 72, 73, 74]

BLOCK_START_EVENTS = [31, 51, 71]

def process_image_era(era_path: str, events_path="./", output_path="./", blocks=2):
    if not era_path:
        print("ERA path empty. Quitting")
        quit()
    print(f"Path received - {era_path}")
    if not os.path.exists(era_path):
        print("ERA path is invalid. Quitting.")
        quit()

    print("Extracting ERA to DataFrame...")
    era_df = pd.read_csv(era_path, delim_whitespace=True)
    era_df = era_df[era_df["Event.Name"].isin(IMAGE_ONSET_EVENTS)]
    print("Done.")

    for i in range(1, blocks + 1):
        print(f"Starting to process block {i}")
        file_name = ""
        for file in os.listdir(events_path):
            if file.endswith(f"task-war_run-{i}_events.tsv"):
                file_name = file
                break
        if not file_name:
            print(f"Event file for round {i} not found in {events_path}. Quitting.")
            quit()
        print(f"Found file {file_name}. Etracting to DataFrame...")
        timing_df = pd.read_csv((events_path + "/" + file_name).replace('//', '/'), sep="\t")
        print("Done.")
        
        aggregated_df = pd.DataFrame(columns=['Event', 'Time', 'Amplitude'])
        df_len = len(era_df)
        block_df = era_df.iloc[df_len - (4 * 3 * 3 * (blocks - i + 1)):df_len - (4 * 3 * 3 * (blocks - i))]

        events = timing_df[timing_df["Biopac"].isin(IMAGE_ONSET_EVENTS)]["Biopac"]
        timings = timing_df[timing_df["Biopac"].isin(IMAGE_ONSET_EVENTS)]["Time"]
        global_means = block_df[block_df["Event.Name"].isin(IMAGE_ONSET_EVENTS)]["Global.Mean"]
        print(global_means)
        cda_tonic = block_df[block_df["Event.Name"].isin(IMAGE_ONSET_EVENTS)]["CDA.Tonic"]
        print(cda_tonic)
        amp = np.round(global_means - cda_tonic, 5)

        new_records = {"Event": events.values,
                        "Time": timings.values,
                        "Amplitude": amp.values}
            
        print(f"Adding new records to aggregated DF...")
        aggregated_df = pd.concat([aggregated_df, pd.DataFrame(new_records)])

        new_timing_name = f"{output_path}/image_scr_run-{i}.txt".replace('//','/')
        aggregated_df.to_csv(new_timing_name, sep="\t", header=False, index=False)


def process_binned_era(era_path: str, events_path="./", output_path="./", blocks=2):
    if not era_path:
        print("ERA path empty. Quitting")
        quit()
    print(f"Path received - {era_path}")
    if not os.path.exists(era_path):
        print("ERA path is invalid. Quitting.")
        quit()

    print("Extracting ERA to DataFrame...")
    era_df = pd.read_csv(era_path, delim_whitespace=True)
    era_df = era_df[era_df["Event.Name"].isin(BLOCK_START_EVENTS)]
    print("Done.")

    for i in range(1, blocks + 1):
        print(f"Starting to process block {i}")
        file_name = ""
        for file in os.listdir(events_path):
            if file.endswith(f"task-war_run-{i}_events.tsv"):
                file_name = file
                break
        if not file_name:
            print(f"Event file for round {i} not found in {events_path}. Quitting.")
            quit()
        print(f"Found file {file_name}. Etracting to DataFrame...")
        timing_df = pd.read_csv((events_path + "/" + file_name).replace('//', '/'), sep="\t")
        print("Done.")
        
        aggregated_df = pd.DataFrame(columns=['Event', 'Time', 'Amplitude'])
        df_len = len(era_df)
        block_df = era_df.iloc[df_len - (3 * 11 * 3 * (blocks - i + 1)):df_len - (3 * 11 * 3 * (blocks - i))]

        for event in BLOCK_START_EVENTS:
            print(f"Processing event {event}...")
            timings = []
            for time in timing_df[timing_df["Biopac"] == event]["Time"]:
                for j in range(11):
                    timings.append(round(time + j * 2, 2))
            global_means = block_df[block_df["Event.Name"] == event]["Global.Mean"]
            cda_tonic = block_df[block_df["Event.Name"] == event]["CDA.Tonic"]
            amp = np.round(global_means - cda_tonic, 5)
            print(f"len timings: {len(timings)}, len amp: {len(amp)}")

            new_records = {"Event": [event] * len(timings),
                            "Time": timings,
                            "Amplitude": amp}
            
            print(f"Adding new records to aggregated DF...")
            aggregated_df = pd.concat([aggregated_df, pd.DataFrame(new_records)])

        new_timing_name = f"{output_path}/binned_scr_run-{i}.txt".replace('//','/')
        aggregated_df.to_csv(new_timing_name, sep="\t", header=True, index=False)
