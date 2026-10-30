import csv

from collections import defaultdict
from datetime import datetime

def bytes_to_gigabytes(bytes_size):
    gigabytes = bytes_size / (1024 ** 3)
    return gigabytes


def process_duplicate_files(input_file, output_file, summary_output_file):
    # Dictionary to store file paths for each hash
    hash_path_dict = defaultdict(list)
    hash_size_dict = {}

    with open(input_file, newline="", encoding="utf-8") as source:
        rows = csv.reader(source, delimiter="\t")
        next(rows, None)
        for hash_value, size, *file_paths in rows:
            hash_path_dict[hash_value].extend(file_paths)
            hash_size_dict[hash_value] = size

    folder_path_files_dict = {}
    # Write the output to the specified file
    for hash_value, paths in hash_path_dict.items():
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
            path_dict = {"filename": file_only, "size": hash_size_dict[hash_value], "folders": file_paths}
            if folder_only in folder_path_files_dict:
                folder_path_files_dict[folder_only].append(path_dict)
            else:
                folder_path_files_dict[folder_only] = [path_dict]

    with open(output_file, "w", newline="", encoding="utf-8") as file:
        with open(summary_output_file, "w", newline="", encoding="utf-8") as summary_file:
            writer = csv.writer(file, delimiter="§", lineterminator="\r\n")
            summary_writer = csv.writer(summary_file, delimiter="§", lineterminator="\r\n")
            header = ["path to folder", "amount of duplicate files in folder",
                      "duplicate file count including all duplicate copies", "folder size of duplicate files",
                      "folder size including all duplicate copies"]
            writer.writerow(header)
            summary_writer.writerow(header)
            for folder in sorted(folder_path_files_dict.keys()):
                files = sorted(folder_path_files_dict[folder], key=lambda x: x['filename'])
                file_count = len(files)
                file_count_with_duplicates = sum([len(f["folders"]) for f in files])
                folder_size_unique = bytes_to_gigabytes(sum([int(f["size"]) for f in files]))
                folder_size_with_duplicates = bytes_to_gigabytes(sum([int(f["size"]) * len(f["folders"]) for f in files]))
                summary_row = [folder, file_count, file_count_with_duplicates,
                               f"{folder_size_unique} GB", f"{folder_size_with_duplicates} GB"]
                writer.writerow(summary_row)
                summary_writer.writerow(summary_row)
                for entry in files:
                    folders = sorted(entry['folders'])
                    writer.writerow([entry['filename'], *(folders or [""])])
                writer.writerow(["---"])


if __name__ == "__main__":
    input_file = "duplicate_files.tsv"
    output_file = f"{datetime.now().strftime('%Y%m%d')}-dropbox-duplicates-formatted.txt"
    summary_output_file = f"{datetime.now().strftime('%Y%m%d')}-dropbox-duplicates-formatted-summary.txt"
    process_duplicate_files(input_file, output_file, summary_output_file)
