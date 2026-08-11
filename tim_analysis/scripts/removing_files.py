import os
import shutil

BASE_PATH_LEDALAB = "/Users/omerdayan/Downloads/1. behavioral MRI"
BOLD_PATH = "/Users/omerdayan/Downloads/tim-bold/3. BOLD"

for item in os.listdir(BASE_PATH_LEDALAB):
    item_path = os.path.join(BASE_PATH_LEDALAB, item)
    try :
        subject = int(item)
    except ValueError:
        print(f"❗️ Skipping {item_path} since it is not a number")
        continue
    if os.path.isdir(item_path):
        print(f"Going over folder {item_path}")
        for file in os.listdir(item_path):
            try:
                shutil.copy(os.path.join(item_path, file), os.path.join(BOLD_PATH, f"sub-{subject}", file))
            except Exception as e:
                print(f"❗️ Error copying {item_path}: {e}")
            else:
                print(f"✅ Copied {file} to {os.path.join(BOLD_PATH, f'sub-{subject}', file)}")