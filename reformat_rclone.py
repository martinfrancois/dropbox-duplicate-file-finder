import csv

from collections import defaultdict
from datetime import datetime

def process_duplicate_files(input_file, output_file):
    # Dictionary to store file paths for each hash
    hash_dict = defaultdict(list)

    # Read input file and populate the hash_dict
    with open(input_file, encoding="utf-8", newline="") as f:
        for line in f:
            # Split by two spaces
            hash_value, file_path = line.rstrip('\r\n').split('  ', 1)
            hash_dict[hash_value].append(file_path)

    folder_path_files_dict = {}
    # Write the output to the specified file
    for hash_value, paths in hash_dict.items():
        for path in paths:
            split_path = path.rsplit('/', 1)
            if len(split_path) > 2 or len(split_path) < 1:
                # should never happen
                breakpoint()
            folder_only = split_path[0]
            file_only = None
            if len(split_path) == 1:
                # file at root level
                file_only = folder_only
                folder_only = '/'
            else:
                file_only = split_path[1]
            file_paths = [file_path for file_path in paths if file_path != path]
            path_dict = {"filename": file_only, "folders": file_paths}
            if folder_only in folder_path_files_dict:
                folder_path_files_dict[folder_only].append(path_dict)
            else:
                folder_path_files_dict[folder_only] = [path_dict]

    with open(output_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter="§", lineterminator="\r\n")
        for folder in sorted(folder_path_files_dict.keys()):
            writer.writerow([folder])
            files = sorted(folder_path_files_dict[folder], key=lambda x: x['filename'])
            for entry in files:
                folders = sorted(entry['folders'])
                writer.writerow([entry['filename'], *(folders or [""])])
            writer.writerow(["---"])


if __name__ == "__main__":
    input_file = "rclone-duplicates.txt"
    output_file = f"{datetime.now().strftime('%Y%m%d')}-dropbox-duplicates-rclone-formatted.txt"
    process_duplicate_files(input_file, output_file)
