import os
import shutil
import re
import sys

def process_directory(root_dir):
    print(f"Scanning directory: {root_dir}")
    for dirpath, dirs, files in os.walk(root_dir):
        if 'tedana' in dirs:
            tedana_path = os.path.join(dirpath, 'tedana')
            
            # Iterate files in tedana
            for file in os.listdir(tedana_path):
                # Pattern: sub-X_ses-Y_task-war_run-Z_space-MNI152NLin2009cAsym_desc-denoised_bold
                match = re.match(r'(sub-[^_]+)_(ses-[^_]+)_task-war_run-([^_]+)_space-MNI152NLin2009cAsym_desc-denoised_bold(\.nii(\.gz)?)', file)
                if match:
                    sub_x = match.group(1)
                    ses_y = match.group(2)
                    run_z = match.group(3)
                    
                    source_file_path = os.path.join(tedana_path, file)
                    
                    # Sibling ses-Y folder
                    sibling_ses_path = os.path.join(dirpath, ses_y)
                    
                    if not os.path.exists(sibling_ses_path):
                        print(f"Warning: Sibling folder {sibling_ses_path} not found for {file}")
                        continue

                    # Target filename
                    target_filename = f"{sub_x}_{ses_y}_task-war_run-{run_z}_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz"
                    
                    # Look for target file in ses-Y or ses-Y/func
                    target_path = None
                    possible_dirs = [
                        os.path.join(sibling_ses_path, 'func'),
                        sibling_ses_path
                    ]
                    
                    found_target = False
                    for d in possible_dirs:
                        possible_path = os.path.join(d, target_filename)
                        if os.path.exists(possible_path):
                            target_path = possible_path
                            found_target = True
                            break
                    
                    if not found_target:
                        print(f"Warning: Target file {target_filename} not found in {sibling_ses_path} or 'func' subdir.")
                        # Default to func if exists, else root of ses
                        func_dir = os.path.join(sibling_ses_path, 'func')
                        if os.path.exists(func_dir):
                            target_path = os.path.join(func_dir, target_filename)
                        else:
                            target_path = os.path.join(sibling_ses_path, target_filename)
                    
                    # Rename if exists
                    if found_target:
                        backup_filename = target_filename.replace('.nii.gz', '_old.nii.gz')
                        backup_path = os.path.join(os.path.dirname(target_path), backup_filename)
                        
                        if not os.path.exists(backup_path):
                            print(f"Renaming {target_path} to {backup_path}")
                            os.rename(target_path, backup_path)
                        else:
                            print(f"Backup file {backup_path} already exists. Skipping rename.")
                            
                    # Copy
                    print(f"Copying {source_file_path} to {target_path}")
                    shutil.copy2(source_file_path, target_path)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        root = sys.argv[1]
    else:
        root = os.getcwd()
    
    process_directory(root)
