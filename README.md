# dropbox-duplicate-file-finder

Lists the files in a Dropbox account that have the same content, grouped by content hash.

## What it does

`__init__.py` walks the whole Dropbox account through the API, one page of entries at a time, and records each file's `content_hash`, size and lowercased path. When the listing is complete it keeps every hash that has more than one path and writes the groups to `duplicate_files.tsv`, one row per hash: hash, size in bytes, then all paths. During a long run it pickles its state to `backup/` every 3000 pages and prints a progress line per page. Rate limit errors wait the time Dropbox asks for; other errors retry up to five times with exponential backoff.

The script only reads. It calls `files_list_folder` and `files_list_folder_continue` and nothing else, so it never deletes, moves or changes a file in Dropbox. What you do with the list is up to you. Its only writes are local: `backup/` and `duplicate_files.tsv`.

Two helper scripts turn a duplicate list into a per-folder view with `§` as the field separator, so a spreadsheet can import it:

- `reformat.py` reads `duplicate_files.tsv` and writes `<date>-dropbox-duplicates-formatted.txt`, with one block per folder that holds duplicates, and `<date>-dropbox-duplicates-formatted-summary.txt`, with only the per-folder totals. Sizes are in GB.
- `reformat_rclone.py` does the same, without sizes, for the output of `rclone hashsum dropbox Dropbox:/ | sort | uniq -w32 -dD > rclone-duplicates.txt`. Use it if you already have rclone set up for the account.

## Requirements

- Python 3.12 or newer (tested with 3.12 and 3.13)
- `dropbox` and `python-dotenv`, pinned in `requirements.txt`
- A Dropbox app with the `files.metadata.read` permission

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

1. Create an app in the [Dropbox App Console](https://www.dropbox.com/developers/apps), grant it `files.metadata.read`, and get an OAuth 2 access token and refresh token for your account.

2. Copy `.env.template` to `.env` and fill in the five values. `DROPBOX_OAUTH2_ACCESS_TOKEN_EXPIRATION` must be an ISO 8601 timestamp such as `2026-01-31T12:00:00`; the script passes it to `datetime.fromisoformat`. `.env` is in `.gitignore`.

3. Create the folder for the state files and run the script from the repository root:

   ```bash
   mkdir -p backup
   python3 __init__.py
   ```

   The result is `duplicate_files.tsv` in the current directory. If `backup/` does not exist, the first state write fails, the retry wrapper walks the whole account again, five attempts in total, and the script ends with `Maximum number of retries (5) exceeded`.

4. Optional: group the result by folder.

   ```bash
   python3 reformat.py
   ```

## Example

`examples/duplicate_files.tsv` is an invented result with two duplicate groups, and `examples/rclone-duplicates.txt` an invented rclone list. Both helper scripts read fixed file names from the current directory, so copy the examples there first.

```bash
cp examples/duplicate_files.tsv examples/rclone-duplicates.txt .
python3 reformat.py
python3 reformat_rclone.py
cat ./*-dropbox-duplicates-formatted.txt
```

The formatted file starts with the `§`-separated header, then for `/archive` the line `report.pdf§/documents/report.pdf`, which says that `/archive/report.pdf` has a copy at `/documents/report.pdf`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

The tests run `__init__.py` against a fake Dropbox client that serves two pages of invented entries, so no network or account is needed. They check the grouping, the TSV output, that the client only receives the two listing calls, and both helper scripts against the examples. Pass `tests` explicitly, because a run from the repository root would try to import `__init__.py` as a package.

## Limitations

- The account walk starts at the root and cannot be limited to a folder without editing `get_all_files("")` at the bottom of `__init__.py`.
- A crash after the last page loses the run; the periodic backup only covers every 3000th page, and nothing reads the backup files back in.
- A retry after a non-rate-limit error restarts the walk from the root but keeps the paths already collected, so every file seen before the error is listed twice and shows up as a duplicate of itself. A group whose paths are all identical is such an artefact, not a duplicate. Run the script again from a clean state if the log shows an `An error (...) occurred, retrying` line.
- `reformat.py` reports sizes as unrounded floats in GB.
- The `§` separator is a plain character in the output, so a path that contains `§` breaks the columns.

## License

MIT, see `LICENSE`.
