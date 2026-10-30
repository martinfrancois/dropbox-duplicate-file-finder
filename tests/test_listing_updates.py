import csv
from pathlib import Path

import dropbox
import pytest

import checkpoints
from file_index import FileIndex
from test_finder import FakeDropbox, HASH_A, HASH_B, HASH_C, file_entry


def folder(path):
    return dropbox.files.FolderMetadata(name=path.rsplit("/", 1)[-1], id="id:" + path, path_lower=path)


def deleted(path):
    return dropbox.files.DeletedMetadata(name=path.rsplit("/", 1)[-1], path_lower=path)


FIRST = [
    file_entry("/changed", HASH_A, 12), file_entry("/repeat", HASH_C, 512),
    file_entry("/delete", HASH_A, 12), file_entry("/tree/child", HASH_A, 12),
    file_entry("/treehouse/keep", HASH_C, 512), file_entry("/file-to-folder", HASH_A, 12),
    file_entry("/folder-to-file/child", HASH_A, 12), file_entry("/implicit-parent", HASH_A, 12),
    file_entry("/keepchildren/child", HASH_C, 512), folder("/keepchildren"),
]
SECOND = [
    file_entry("/repeat", HASH_C, 512), file_entry("/changed", HASH_B, 24),
    deleted("/delete"), deleted("/tree"), folder("/file-to-folder"),
    file_entry("/file-to-folder/child", HASH_B, 24), file_entry("/folder-to-file", HASH_B, 24),
    file_entry("/implicit-parent/child", HASH_C, 512), folder("/keepchildren"), deleted("/missing"),
]
THIRD = [
    file_entry("/repeat", HASH_C, 512), deleted("/file-to-folder/child"),
    deleted("/folder-to-file"), file_entry("/copy", HASH_B, 24),
]
EXPECTED = {
    HASH_C: ["/repeat", "/treehouse/keep", "/keepchildren/child", "/implicit-parent/child"],
    HASH_B: ["/changed", "/copy"],
}


@pytest.mark.parametrize("mode", ["uninterrupted", "resume", "retry"])
def test_ordered_listing_updates_produce_same_checkpoint_and_tsv(finder, tmp_path, monkeypatch, mode):
    directory = tmp_path / mode
    directory.mkdir()
    monkeypatch.chdir(directory)
    calls = []

    class Updating(FakeDropbox):
        failed = False
        interrupt = mode == "resume"

        def files_list_folder(self, path, recursive=False):
            calls.append("root")
            return dropbox.files.ListFolderResult(entries=FIRST, cursor="one", has_more=True)

        def files_list_folder_continue(self, cursor):
            calls.append(cursor)
            if self.interrupt:
                raise KeyboardInterrupt
            if cursor == "one":
                return dropbox.files.ListFolderResult(entries=SECOND, cursor="two", has_more=True)
            if mode == "retry" and not self.failed:
                self.failed = True
                raise OSError("synthetic interruption after unsaved updates")
            return dropbox.files.ListFolderResult(entries=THIRD, cursor="three", has_more=False)

    client = Updating()
    monkeypatch.setattr(dropbox, "Dropbox", lambda **kwargs: client)
    if mode == "resume":
        monkeypatch.setattr(finder, "BACKUP_EVERY_X_FETCHES", 1)
        with pytest.raises(KeyboardInterrupt):
            finder.main([])
        assert checkpoints.load_checkpoint()["count"] == 9
        client.interrupt = False
        finder.main(["--resume"])
        assert calls == ["root", "one", "one", "two"]
    elif mode == "retry":
        index = FileIndex(checkpoints.empty_checkpoint())
        for entry in FIRST:
            index.apply(entry)
        checkpoints.write_checkpoint(index.checkpoint("one", complete=False))
        finder.main(["--resume"])
        assert calls == ["one", "two", "one", "two"]
    else:
        finder.main([])
        assert calls == ["root", "one", "two"]
    state = checkpoints.load_checkpoint()
    assert state["paths"] == EXPECTED
    assert state["sizes"] == {HASH_C: 512, HASH_B: 24}
    assert state["count"] == finder.count["file"] == 6
    assert state["complete"] is True
    assert state["cursor"] is None
    with Path("duplicate_files.tsv").open(newline="") as stream:
        assert list(csv.reader(stream, delimiter="\t")) == [
            ["Hash", "Size", "Paths"],
            [HASH_C, "512", *EXPECTED[HASH_C]],
            [HASH_B, "24", *EXPECTED[HASH_B]],
        ]


def test_repeated_metadata_does_not_count_the_same_path_twice():
    index = FileIndex(checkpoints.empty_checkpoint())
    entry = file_entry("/one", HASH_A, 12)
    index.apply(entry)
    index.apply(entry)
    state = index.checkpoint(None, complete=True)
    assert state["paths"] == {HASH_A: ["/one"]}
    assert state["count"] == 1
    checkpoints.validate(state)


def test_file_update_removes_children_even_if_legacy_state_has_same_hash():
    state = checkpoints.empty_checkpoint()
    state.update(paths={HASH_A: ["/parent", "/parent/child"]}, sizes={HASH_A: 12}, count=2, cursor="saved")
    index = FileIndex(state)
    index.apply(file_entry("/parent", HASH_A, 12))
    assert index.checkpoint(None, complete=True)["paths"] == {HASH_A: ["/parent"]}
    assert len(index.hash_by_path) == 1


@pytest.mark.parametrize("path", [None, "relative", "/a/../b"])
def test_missing_or_invalid_metadata_path_preserves_index(path):
    index = FileIndex(checkpoints.empty_checkpoint())
    original = file_entry("/original", HASH_A, 12)
    index.apply(original)
    invalid = file_entry("/invalid", HASH_B, 24)
    invalid.path_lower = path
    with pytest.raises(checkpoints.CheckpointError):
        index.apply(invalid)
    assert index.checkpoint(None, complete=True)["paths"] == {HASH_A: ["/original"]}


def test_parent_iteration_terminates_for_relative_input():
    assert list(FileIndex.parents("relative")) == []
