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
    era_df = pd.read_csv(era_path, sep="\t")
    era_df = era_df[era_df["Event.Name"].isin(IMAGE_ONSET_EVENTS)]
    print("Done.")

    for i in range(1, blocks + 1):
        print(f"Starting to process block {i}")
        file_name = ""
        for file in os.listdir(events_path):
            if file.endswith(f"task-war_run-{i}_events.tsv"):
                file_name = file
                break
        if not file:
            print(f"Event file for round {i} not found in {events_path}. Quitting.")
            quit()
        print(f"Found file {file_name}. Etracting to DataFrame...")
        timing_df = pd.read_csv((events_path + "/" + file_name).replace('//', '/'), sep="\t")
        print("Done.")
        
        aggregated_df = pd.DataFrame(columns=['Event', 'Time', 'Amplitude'])
        block_df = era_df.iloc[(4 * 3 * 3 * (i - 1)) : (4 * 3 * 3 * i),:]

        for event in IMAGE_ONSET_EVENTS:
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
    era_df = pd.read_csv(era_path, sep="\t")
    era_df = era_df[era_df["Event.Name"].isin(BLOCK_START_EVENTS)]
    print("Done.")

    for i in range(1, blocks + 1):
        print(f"Starting to process block {i}")
        file_name = ""
        for file in os.listdir(events_path):
            if file.endswith(f"task-war_run-{i}_events.tsv"):
                file_name = file
                break
        if not file:
            print(f"Event file for round {i} not found in {events_path}. Quitting.")
            quit()
        print(f"Found file {file_name}. Etracting to DataFrame...")
        timing_df = pd.read_csv((events_path + "/" + file_name).replace('//', '/'), sep="\t")
        print("Done.")
        
        aggregated_df = pd.DataFrame(columns=['Event', 'Time', 'Amplitude'])
        block_df = era_df.iloc[(3 * 11 * 3 * (i - 1)) : (3 * 11 * 3 * i),:]

        for event in BLOCK_START_EVENTS:
            print(f"Processing event {event}...")
            timings = []
            for time in timing_df[timing_df["condition"] == event]["onset"]:
                for j in range(11):
                    timings.append(time + j * 2)
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

        new_timing_name = f"{output_path}/binned_scr_run-{i}.txt".replace('//','/')
        aggregated_df.to_csv(new_timing_name, sep="\t", header=False, index=False)
