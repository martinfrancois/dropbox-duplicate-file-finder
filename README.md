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

## Reading formatted reports

Both formatters write UTF-8 CSV records with `§` as the delimiter and `"` as the quote character. Fields containing a separator, quote, or line break are quoted; embedded quotes are doubled. Do not parse these reports with `split("§")` or split them into physical lines first. For example:

```python
import csv

with open("report.txt", newline="", encoding="utf-8") as report:
    rows = list(csv.reader(report, delimiter="§"))
```

The summary report has five columns on every record, including the header. The detailed Dropbox report starts with that header, then repeats a five-column folder summary, file records containing a filename and its duplicate paths, and a single-field `---` record. The rclone report has a one-field folder record instead of a summary/header. Read the folder record at the start of each block; subsequent file records always have at least two fields, so a filename `---` is not a block terminator.

Simple filenames and paths keep their existing field values. Record endings are now standard CSV CRLF; consumers that require the previous LF byte format must normalize record endings after parsing. The Dropbox input is tab-delimited CSV as written by the finder, including quoted tabs and line breaks. Rclone input remains one hash, two spaces, and a path per physical line, so it cannot represent embedded line breaks. Leading and trailing spaces in those paths are retained.

## Tests

```
pip3 install -r requirements-dev.txt
python3 -m pytest
```

The tests run `find_duplicates.py` against a fake Dropbox client, so they need no account or network. Importing the module does not load credentials, create a client, or write files.

The finder command changed from `python3 __init__.py` to `python3 find_duplicates.py`. Update existing shell scripts to use the named entry point.

## Interrupted scans and recovery

The finder saves `backup/checkpoint.json` after every 3000 pages and after the last page. It contains a version, cursor, collected paths and sizes, current-file count, and completion flag in one atomic JSON replacement. Entries are applied in order: repeated paths update existing files, folder entries replace files while retaining children, and deletion entries remove paths and their subtrees. Counts describe the files currently present in the collected state. Saved entries have already been applied. Resume starts with the page after the saved cursor; it does not replay those entries:

```sh
python3 find_duplicates.py --resume
```

An interruption loses only work since the latest checkpoint. If no checkpoint exists yet, run the normal command again. A completed checkpoint can regenerate `duplicate_files.tsv` without listing the account. The TSV also uses atomic replacement so an interrupted write does not replace an earlier complete report.

Normal startup refuses to overwrite saved state. Invalid or expired checkpoints produce a diagnostic and remain intact. To start over, archive the entire backup directory and scan again:

```sh
python3 find_duplicates.py --restart
```

This moves the old directory to `backup.previous-<unique id>`. Keep or remove that archive yourself. Use the same account and app credentials when resuming. Only one finder process can run in a working directory; `.finder.lock` is a persistent lock file, not a checkpoint. The operating system releases its lock when the process exits, including after a crash.

Older versions wrote two bz2-compressed pickle dictionaries plus `cursor.txt` and `entries.txt`. To migrate a complete set left by one completed checkpoint write:

```sh
python3 find_duplicates.py --resume-legacy
```

Migration reads only primitive dictionaries and the cursor through a restricted unpickler, validates their consistency, and derives the count from saved paths. `entries.txt` must exist, but its contents are not unpickled or replayed because that page was already processed. An empty old cursor marks a completed scan. All old files stay intact alongside the new JSON checkpoint. Old writes were not atomic across files, so the program cannot prove that they all came from the same moment. If they were copied from different runs or the write was interrupted, use `--restart` instead. New checkpoints avoid that ambiguity.

## Limitations

- The script walks the whole account from the root; folder-limited scans are not supported.
- `reformat.py` writes sizes in GB as unrounded numbers.

## License

MIT, see [LICENSE](LICENSE).
