# dropbox-duplicate-file-finder

This is a simple Python script that finds duplicate files in a Dropbox folder.
It uses the Dropbox API to get the list of files and their hashes, and then compares the hashes to find duplicates.

## Files

- `__init__.py`: The main script.
- `reformat.py`: A script to reformat the output of the main script into a format that can be read into Excel using `§` as a delimiter.
- `reformat_rclone.py`: A script to reformat the output of running `rclone hashsum dropbox Dropbox:/ | sort | uniq -w32 -dD > rclone-duplicates.txt`

## Usage

1. Install the dependencies from the requirements file:

```
pip3 install -r requirements.txt
```

2. Create a new app on the [Dropbox developer console](https://www.dropbox.com/developers/apps) and generate an access token.

3. Add the details of the app and the access token to a `.env` file in the root of the project, by copying the `.env.template` file and filling in the details.

4. Run the script:

```
python3 __init__.py
```