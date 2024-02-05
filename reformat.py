from collections import defaultdict
from datetime import datetime

def bytes_to_gigabytes(bytes_size):
    gigabytes = bytes_size / (1024 ** 3)
    return gigabytes


def process_duplicate_files(input_file, output_file, summary_output_file):
    # Dictionary to store file paths for each hash
    hash_path_dict = defaultdict(list)
    hash_size_dict = {}

    # Read input file and populate the hash_path_dict
    with open(input_file, 'r') as f:
        for line_num, line in enumerate(f):
            if line_num == 0:
                # Skip header row
                continue
            # Split by two spaces
            hash_value, size, *file_paths = line.strip().split('\t')
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

    with open(output_file, "w") as file:
        with open(summary_output_file, "w") as summary_file:
            header = "path to folder§amount of duplicate files in folder§duplicate file count including all duplicate copies§folder size of duplicate files§folder size including all duplicate copies"
            file.write(f"{header}\n")
            summary_file.write(f"{header}\n")
            for folder in sorted(folder_path_files_dict.keys()):
                files = sorted(folder_path_files_dict[folder], key=lambda x: x['filename'])
                file_count = len(files)
                file_count_with_duplicates = sum([len(f["folders"]) for f in files])
                folder_size_unique = bytes_to_gigabytes(sum([int(f["size"]) for f in files]))
                folder_size_with_duplicates = bytes_to_gigabytes(sum([int(f["size"]) * len(f["folders"]) for f in files]))
                summary_text = f"{folder}§{file_count}§{file_count_with_duplicates}§{folder_size_unique} GB§{folder_size_with_duplicates} GB\n"
                file.write(summary_text)
                summary_file.write(summary_text)
                for entry in files:
                    folders = sorted(entry['folders'])
                    file.write(f"{entry['filename']}§{'§'.join(folders)}\n")
                file.write("---\n")


if __name__ == "__main__":
    input_file = "duplicate_files.tsv"
    output_file = f"{datetime.now().strftime('%Y%m%d')}-dropbox-duplicates-formatted.txt"
    summary_output_file = f"{datetime.now().strftime('%Y%m%d')}-dropbox-duplicates-formatted-summary.txt"
    process_duplicate_files(input_file, output_file, summary_output_file)
