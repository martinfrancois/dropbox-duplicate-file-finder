# Import the required modules
import datetime
import dropbox
import csv
import random
import time
import bz2
import os
import pickle
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


def serialize_data(data, filename, with_compression=False):
    """Serialize data and write it to a file."""
    mode = 'wb'
    if with_compression:
        with bz2.BZ2File(filename, mode) as file:
            pickle.dump(data, file)
    else:
        with open(filename, mode) as file:
            pickle.dump(data, file)


def deserialize_data(filename):
    """Deserialize data from a file."""
    with open(filename, 'rb') as file:
        return pickle.load(file)


def backup(cursor, entries):
    print("Backing up...")
    serialize_data(hash_to_path_dict, 'backup/hash_to_path_dict.txt', True)
    serialize_data(hash_to_size_dict, 'backup/hash_to_size_dict.txt', True)
    serialize_data(cursor, 'backup/cursor.txt')
    serialize_data(entries, 'backup/entries.txt')


# Define a function to get all the files in a folder
def get_all_files(folder_path):
    # A retry starts at the root, so results from the earlier attempt must not survive.
    hash_to_path_dict.clear()
    hash_to_size_dict.clear()
    count["file"] = 0
    start = time.time()
    # Get all the folder's metadata and the entries recursively, to retrieve all files in all subfolders
    result = dbx.files_list_folder(folder_path, recursive=True)
    entries = result.entries
    fetch_count = 1
    # Loop through the entries
    while True:
        for entry in entries:
            # If the entry is a file, add its path and metadata to the dictionary and the list
            if isinstance(entry, dropbox.files.FileMetadata):
                count["file"] += 1
                add_entry(entry)
        # If there are more entries, get the next batch
        if result.has_more:
            fetch_count += 1
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Fetching more | fetches: {str(fetch_count)} | files: {str(count['file'])}")
            cursor = result.cursor
            if fetch_count % BACKUP_EVERY_X_FETCHES == 0:
                processing_stats(start)
                backup(cursor, entries)
            result = dbx.files_list_folder_continue(cursor)
            entries = result.entries
        # Otherwise, break the loop
        else:
            print("No more entries!")
            break
    backup("", entries)
    processing_stats(start)
    print("Finished get_all_files")


# Define a function to find duplicate files
def find_duplicate_files():
    print("Find duplicate files")
    # Filter out hashes for which there is only one path, as they are not duplicates
    filtered_dict = {key: values for key, values in hash_to_path_dict.items() if len(values) > 1}
    serialize_data(filtered_dict, "backup/filtered_dict.txt")
    return filtered_dict


# Define a function to save the duplicate files to a tsv file
def save_duplicate_files(file_name):
    print("Save duplicate files")
    # Open a tsv file in write mode
    with open(file_name, 'w', newline='') as file:
        writer = csv.writer(file, delimiter='\t')

        # Write the header
        writer.writerow(['Hash', 'Size', 'Paths'])

        # Write the key-value pairs
        for hash_key, paths in duplicate_files.items():
            writer.writerow([hash_key, str(hash_to_size_dict[hash_key])] + paths)


# Define a function to retry with exponential backoff
def retry_with_backoff(fn, retries=5, backoff_in_seconds=1):
    # Initialize the number of attempts
    attempts = 0
    # Loop until the maximum number of retries is reached
    while attempts < retries:
        try:
            # Try to execute the function and return the result
            return fn()
        except Exception as e:
            # If the exception is any other error, calculate the delay using exponential backoff with jitter
            delay = (backoff_in_seconds * 2 ** attempts) + random.uniform(0, 1)
            print(f"An error ({e}) occurred, retrying after {delay} seconds")
            time.sleep(delay)
        # Increment the number of attempts
        attempts += 1
    # If the maximum number of retries is reached, raise an exception
    raise Exception(f"Maximum number of retries ({retries}) exceeded")


def main():
    global dbx, duplicate_files
    load_dotenv()
    dbx = dropbox.Dropbox(
        oauth2_access_token=os.getenv("DROPBOX_OAUTH2_ACCESS_TOKEN"),
        oauth2_access_token_expiration=datetime.datetime.fromisoformat(
            os.getenv("DROPBOX_OAUTH2_ACCESS_TOKEN_EXPIRATION")),
        oauth2_refresh_token=os.getenv("DROPBOX_OAUTH2_REFRESH_TOKEN"),
        app_key=os.getenv("DROPBOX_APP_KEY"),
        app_secret=os.getenv("DROPBOX_APP_SECRET"),
    )
    os.makedirs("backup", exist_ok=True)
    retry_with_backoff(lambda: get_all_files(""))
    duplicate_files = find_duplicate_files()
    save_duplicate_files("duplicate_files.tsv")
    print("The duplicate files have been saved to duplicate_files.tsv")


if __name__ == "__main__":
    main()
