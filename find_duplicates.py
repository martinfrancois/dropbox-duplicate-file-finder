# Import the required modules
import datetime
import dropbox
import csv
import random
import time
import os
import argparse
import tempfile

import checkpoints
from dotenv import load_dotenv

BACKUP_EVERY_X_FETCHES = 3000

dbx = None

# Initialize an empty dictionary to store the content hashes and the file paths
hash_to_path_dict = {}
# Initialize an empty dictionary to store the content hashes and the file size
hash_to_size_dict = {}
# Initialize a dict to count the amount of files processed so far
count = {"file": 0}


def add_entry(entry):
    file_hash = entry.content_hash
    file_path = entry.path_lower

    hash_to_size_dict[file_hash] = entry.size

    # If the content hash is already in the dictionary, append the file path to the list
    if file_hash in hash_to_path_dict:
        hash_to_path_dict[file_hash].append(file_path)
    # Otherwise, create a new entry with the content hash and the file path
    else:
        hash_to_path_dict[file_hash] = [file_path]


def processing_stats(start):
    end = time.time()
    print(f"Files processed per second on average: {count['file'] / (end - start)}")


def get_all_files(folder_path):
    if folder_path != "":
        raise ValueError('cannot scan folder: checkpoint recovery currently supports the account root only')
    state = checkpoints.load_checkpoint() if checkpoints.CHECKPOINT.exists() else checkpoints.empty_checkpoint()
    hash_to_path_dict.clear()
    hash_to_path_dict.update(state["paths"])
    hash_to_size_dict.clear()
    hash_to_size_dict.update(state["sizes"])
    count["file"] = state["count"]
    if state["complete"]:
        return
    start = time.time()
    cursor = state["cursor"]
    fetch_count = 0
    while True:
        try:
            result = dbx.files_list_folder_continue(cursor) if cursor else dbx.files_list_folder(folder_path, recursive=True)
        except dropbox.exceptions.ApiError as error:
            if isinstance(error.error, dropbox.files.ListFolderContinueError) and error.error.is_reset():
                raise checkpoints.CheckpointError('cannot resume checkpoint "backup/checkpoint.json": Dropbox expired the cursor; use --restart to preserve it and scan again') from error
            raise
        for entry in result.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                count["file"] += 1
                add_entry(entry)
        fetch_count += 1
        cursor = result.cursor if result.has_more else None
        if fetch_count % BACKUP_EVERY_X_FETCHES == 0 or not result.has_more:
            state.update(paths=hash_to_path_dict, sizes=hash_to_size_dict, count=count["file"],
                         cursor=cursor, complete=not result.has_more)
            checkpoints.write_checkpoint(state)
        if not result.has_more:
            break
    processing_stats(start)
    print("Finished get_all_files")


# Define a function to find duplicate files
def find_duplicate_files():
    print("Find duplicate files")
    # Filter out hashes for which there is only one path, as they are not duplicates
    filtered_dict = {key: values for key, values in hash_to_path_dict.items() if len(values) > 1}
    return filtered_dict


# Define a function to save the duplicate files to a tsv file
def save_duplicate_files(file_name):
    # Replace only after the full TSV is written so an interrupted export is retryable.
    fd, temporary = tempfile.mkstemp(prefix=".duplicates-", suffix=".tmp", dir=".")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, delimiter="\t")
            writer.writerow(["Hash", "Size", "Paths"])
            for hash_key, paths in duplicate_files.items():
                writer.writerow([hash_key, str(hash_to_size_dict[hash_key])] + paths)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, file_name)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


# Define a function to retry with exponential backoff
def retry_with_backoff(fn, retries=5, backoff_in_seconds=1):
    # Initialize the number of attempts
    attempts = 0
    last_error = None
    # Loop until the maximum number of retries is reached
    while attempts < retries:
        try:
            # Try to execute the function and return the result
            return fn()
        except checkpoints.CheckpointError:
            raise
        except Exception as e:
            last_error = e
            # If the exception is any other error, calculate the delay using exponential backoff with jitter
            delay = (backoff_in_seconds * 2 ** attempts) + random.uniform(0, 1)
            print(f"cannot complete listing: retrying after {delay:.1f} seconds")
            time.sleep(delay)
        # Increment the number of attempts
        attempts += 1
    # If the maximum number of retries is reached, raise an exception
    raise RuntimeError(f"cannot complete listing: exhausted {retries} attempts; use --resume if a checkpoint exists") from last_error


def main(argv=None):
    global dbx, duplicate_files
    parser = argparse.ArgumentParser(description="Find duplicate Dropbox files without changing the account")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--resume", action="store_true", help="Continue the saved scan or regenerate its TSV")
    modes.add_argument("--restart", action="store_true", help="Archive saved state and start a fresh scan")
    modes.add_argument("--resume-legacy", action="store_true", help="Migrate a consistent legacy checkpoint set and resume")
    args = parser.parse_args(argv)
    try:
        with checkpoints.scan_lock():
            checkpoints.prepare_run(resume=args.resume, restart=args.restart, resume_legacy=args.resume_legacy)
            load_dotenv()
            dbx = dropbox.Dropbox(
                oauth2_access_token=os.getenv("DROPBOX_OAUTH2_ACCESS_TOKEN"),
                oauth2_access_token_expiration=datetime.datetime.fromisoformat(
                    os.getenv("DROPBOX_OAUTH2_ACCESS_TOKEN_EXPIRATION")),
                oauth2_refresh_token=os.getenv("DROPBOX_OAUTH2_REFRESH_TOKEN"),
                app_key=os.getenv("DROPBOX_APP_KEY"),
                app_secret=os.getenv("DROPBOX_APP_SECRET"),
            )
            retry_with_backoff(lambda: get_all_files(""))
            duplicate_files = find_duplicate_files()
            save_duplicate_files("duplicate_files.tsv")
            print("The duplicate files have been saved to duplicate_files.tsv")
    except checkpoints.CheckpointError as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
