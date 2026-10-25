import csv
import importlib.util
import time
from pathlib import Path

import dropbox
import pytest

ROOT = Path(__file__).resolve().parent.parent

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def file_entry(path, content_hash, size):
    return dropbox.files.FileMetadata(
        name=path.rsplit("/", 1)[-1],
        id="id:" + path.strip("/").replace("/", "-"),
        path_lower=path,
        content_hash=content_hash,
        size=size,
    )


PAGE_ONE = [
    dropbox.files.FolderMetadata(name="photos", id="id:photos", path_lower="/photos"),
    file_entry("/photos/img_0001.jpg", HASH_A, 2048),
    file_entry("/photos/2024/img_0001.jpg", HASH_A, 2048),
    file_entry("/notes.txt", HASH_B, 12),
]

PAGE_TWO = [
    file_entry("/backup/img_0001.jpg", HASH_A, 2048),
    file_entry("/documents/report.pdf", HASH_C, 512),
    file_entry("/archive/report.pdf", HASH_C, 512),
]


class FakeDropbox:
    """Answers the two listing calls the script makes and nothing else."""

    def __init__(self, **kwargs):
        self.calls = []

    def files_list_folder(self, path, recursive=False):
        self.calls.append(("files_list_folder", path, recursive))
        return dropbox.files.ListFolderResult(entries=PAGE_ONE, cursor="cursor-1", has_more=True)

    def files_list_folder_continue(self, cursor):
        self.calls.append(("files_list_folder_continue", cursor))
        return dropbox.files.ListFolderResult(entries=PAGE_TWO, cursor="cursor-2", has_more=False)


@pytest.fixture
def finder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("DROPBOX_OAUTH2_ACCESS_TOKEN", "unused")
    monkeypatch.setenv("DROPBOX_OAUTH2_ACCESS_TOKEN_EXPIRATION", "2030-01-01T00:00:00")
    monkeypatch.setenv("DROPBOX_OAUTH2_REFRESH_TOKEN", "unused")
    monkeypatch.setenv("DROPBOX_APP_KEY", "unused")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "unused")
    monkeypatch.setattr(dropbox, "Dropbox", FakeDropbox)

    spec = importlib.util.spec_from_file_location("finder", ROOT / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_groups_files_by_content_hash_and_keeps_only_duplicates(finder):
    assert finder.duplicate_files == {
        HASH_A: ["/photos/img_0001.jpg", "/photos/2024/img_0001.jpg", "/backup/img_0001.jpg"],
        HASH_C: ["/documents/report.pdf", "/archive/report.pdf"],
    }
    assert finder.hash_to_size_dict[HASH_A] == 2048
    assert finder.count["file"] == 6


def test_writes_one_tsv_row_per_duplicate_group(finder, tmp_path):
    with (tmp_path / "duplicate_files.tsv").open(newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))

    assert rows == [
        ["Hash", "Size", "Paths"],
        [HASH_A, "2048", "/photos/img_0001.jpg", "/photos/2024/img_0001.jpg", "/backup/img_0001.jpg"],
        [HASH_C, "512", "/documents/report.pdf", "/archive/report.pdf"],
    ]


def test_only_lists_and_never_deletes(finder):
    assert finder.dbx.calls == [
        ("files_list_folder", "", True),
        ("files_list_folder_continue", "cursor-1"),
    ]


def test_missing_backup_directory_is_created(finder, tmp_path):
    assert (tmp_path / "backup" / "filtered_dict.txt").is_file()
    assert finder.count["file"] == 6
