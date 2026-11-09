# AGENTS.md

dropbox-duplicate-file-finder lists the files in a Dropbox account that have the same content, grouped by content hash. It only reads from Dropbox; see [README.md](README.md).

## Checks

```
pip3 install -r requirements-dev.txt
python3 -m pytest
cp examples/duplicate_files.tsv examples/rclone-duplicates.txt .
python3 reformat.py
python3 reformat_rclone.py
```

The tests run `find_duplicates.py` against a fake Dropbox client, so they need no account or network. The last three commands are the README example that CI also runs. The `cp` overwrites any real `duplicate_files.tsv` or `rclone-duplicates.txt` in the working directory, so check for one first.

## Contributing for Someone Else

martinfrancois's rule for outside contributions, and for any agent working for an outside contributor: contributors shouldn't spend time on pull requests that collide with someone else's work or that he wouldn't accept. So a contribution takes one of three paths (see "Three ways to contribute" in CONTRIBUTING.md):

- Small fix (bug fix, typo, docs improvement or similar): open a pull request directly, no issue needed. If an issue for it exists, claim it first as below.
- Existing issue: check its assignees and linked pull requests, post `/take` on the issue, and start only once the assignment comes back. Never open a pull request for an issue that isn't assigned to the contributor you work for, and don't start on one that someone else holds or that an open pull request already addresses.
- New feature: open a thread in the Ideas category of GitHub Discussions. Wait until martinfrancois approves it and opens an issue, then claim that issue with `/take`. Never open a feature pull request without an approved issue assigned to your contributor.
