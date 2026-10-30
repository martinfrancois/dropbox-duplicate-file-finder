# dropbox-duplicate-file-finder

This is a simple Python script that finds duplicate files in a Dropbox account.
It uses the Dropbox API to get the list of files and their hashes, and then compares the hashes to find duplicates.

The script only reads. Its only API calls are `files_list_folder` and `files_list_folder_continue`, so it never deletes, moves or changes anything in Dropbox.

## Files

- `find_duplicates.py`: The main script. It writes the duplicates to `duplicate_files.tsv`, one row per content hash with the size in bytes and all paths, and saves its state to `backup/` along the way.
- `reformat.py`: A script to reformat the output of the main script into a format that can be read into Excel using `§` as a delimiter. It writes `<date>-dropbox-duplicates-formatted.txt`, with one block per folder that holds duplicates, and `<date>-dropbox-duplicates-formatted-summary.txt`, with only the totals per folder.
- `reformat_rclone.py`: A script to reformat the output of running `rclone hashsum dropbox Dropbox:/ | sort | uniq -w32 -dD > rclone-duplicates.txt` the same way, without sizes, into `<date>-dropbox-duplicates-rclone-formatted.txt`.

## Usage

1. Install the dependencies from the requirements file. CI tests with Python 3.12.

```
pip3 install -r requirements.txt
```

2. Create a new app on the [Dropbox developer console](https://www.dropbox.com/developers/apps), give it the `files.metadata.read` permission, and generate an access token and a refresh token for your account.

3. Add the details of the app and the tokens to a `.env` file in the root of the project, by copying the `.env.template` file and filling in the details. `DROPBOX_OAUTH2_ACCESS_TOKEN_EXPIRATION` is an ISO 8601 timestamp such as `2026-01-31T12:00:00`.

4. Run the script. It creates the folder for its state files:

```
python3 find_duplicates.py
```

The duplicates end up in `duplicate_files.tsv`.

5. Optional: run `python3 reformat.py` in the same folder to group the result by folder.

## Example

`examples/` has an invented `duplicate_files.tsv` and an invented `rclone-duplicates.txt`. The helper scripts read these file names from the current folder, so copy them there first:

```
cp examples/duplicate_files.tsv examples/rclone-duplicates.txt .
python3 reformat.py
python3 reformat_rclone.py
```

In the formatted file, the `/archive` block has the line `report.pdf§/documents/report.pdf`, which means that `/archive/report.pdf` has a copy at `/documents/report.pdf`.

## Tests

```
pip3 install -r requirements-dev.txt
python3 -m pytest
```

The tests run `find_duplicates.py` against a fake Dropbox client, so they need no account or network. Importing the module does not load credentials, create a client, or write files.

The finder command changed from `python3 __init__.py` to `python3 find_duplicates.py`. Update existing shell scripts to use the named entry point.

## Limitations

- The script always walks the whole account from the root. To limit it to a folder, change `get_all_files("")` at the bottom of `find_duplicates.py`.
- Nothing reads the backup files back in, so a crash after the last page loses the run.
- `reformat.py` writes sizes in GB as unrounded numbers.
- A path that contains `§` breaks the columns of the reformatted output.

## License

MIT, see [LICENSE](LICENSE).
