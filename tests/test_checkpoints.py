import bz2
import json
from pathlib import Path
import pickle

import dropbox
import pytest

import checkpoints
from test_finder import FakeDropbox, HASH_A, PAGE_ONE, PAGE_TWO


def partial_state():
    files = [entry for entry in PAGE_ONE if isinstance(entry, dropbox.files.FileMetadata)]
    state = checkpoints.empty_checkpoint()
    for entry in files:
        state["paths"].setdefault(entry.content_hash, []).append(entry.path_lower)
        state["sizes"][entry.content_hash] = entry.size
    state.update(count=len(files), cursor="cursor-1")
    return state


def test_interrupted_resume_matches_uninterrupted_tsv(finder, tmp_path, monkeypatch):
    expected = Path("duplicate_files.tsv").read_bytes()
    interrupted = tmp_path / "interrupted"
    interrupted.mkdir()
    monkeypatch.chdir(interrupted)
    monkeypatch.setattr(finder, "BACKUP_EVERY_X_FETCHES", 1)

    class Interrupted(FakeDropbox):
        def files_list_folder_continue(self, cursor):
            raise KeyboardInterrupt

    monkeypatch.setattr(dropbox, "Dropbox", Interrupted)
    with pytest.raises(KeyboardInterrupt):
        finder.main([])
    assert checkpoints.load_checkpoint() == partial_state()

    class ResumeOnly(FakeDropbox):
        def files_list_folder(self, *args, **kwargs):
            pytest.fail("resume must not start again at the root")

    monkeypatch.setattr(dropbox, "Dropbox", ResumeOnly)
    finder.main(["--resume"])
    assert finder.dbx.calls == [("files_list_folder_continue", "cursor-1")]
    assert finder.count["file"] == 6
    assert Path("duplicate_files.tsv").read_bytes() == expected
    assert checkpoints.load_checkpoint()["complete"] is True


def test_completed_resume_regenerates_tsv_without_listing(finder, monkeypatch):
    expected = Path("duplicate_files.tsv").read_bytes()
    Path("duplicate_files.tsv").unlink()

    class NoListing(FakeDropbox):
        def files_list_folder(self, *args, **kwargs):
            pytest.fail("completed resume must not list the account")

        files_list_folder_continue = files_list_folder

    monkeypatch.setattr(dropbox, "Dropbox", NoListing)
    finder.main(["--resume"])
    assert finder.count["file"] == 6
    assert Path("duplicate_files.tsv").read_bytes() == expected


def test_fresh_run_refuses_saved_state_before_client_creation(finder, monkeypatch, capsys):
    before = checkpoints.CHECKPOINT.read_bytes()
    monkeypatch.setattr(dropbox, "Dropbox", lambda **kwargs: pytest.fail("client created before overwrite refusal"))
    with pytest.raises(SystemExit) as error:
        finder.main([])
    assert error.value.code == 2
    assert "--resume" in capsys.readouterr().err
    assert checkpoints.CHECKPOINT.read_bytes() == before


@pytest.mark.parametrize("contents", [b"not json", b'{}', b'{"version":99}'])
def test_invalid_resume_preserves_saved_bytes(finder, contents, capsys):
    checkpoints.CHECKPOINT.write_bytes(contents)
    with pytest.raises(SystemExit) as error:
        finder.main(["--resume"])
    assert error.value.code == 2
    assert "--restart" in capsys.readouterr().err
    assert checkpoints.CHECKPOINT.read_bytes() == contents


@pytest.mark.parametrize("change", ["count", "duplicate", "sizes", "cursor"])
def test_inconsistent_checkpoint_is_rejected(tmp_path, monkeypatch, change):
    monkeypatch.chdir(tmp_path)
    state = partial_state()
    if change == "count":
        state["count"] += 1
    elif change == "duplicate":
        state["paths"][HASH_A].append(state["paths"][HASH_A][0])
        state["count"] += 1
    elif change == "sizes":
        state["sizes"].clear()
    else:
        state["cursor"] = None
    with pytest.raises(ValueError):
        checkpoints.validate(state)


def test_expired_cursor_is_not_retried_or_overwritten(finder, monkeypatch, capsys):
    checkpoints.write_checkpoint(partial_state())
    before = checkpoints.CHECKPOINT.read_bytes()
    calls = []

    class Expired(FakeDropbox):
        def files_list_folder_continue(self, cursor):
            calls.append(cursor)
            raise dropbox.exceptions.ApiError("synthetic", dropbox.files.ListFolderContinueError.reset, None, None)

    monkeypatch.setattr(dropbox, "Dropbox", Expired)
    with pytest.raises(SystemExit) as error:
        finder.main(["--resume"])
    assert error.value.code == 2
    assert calls == ["cursor-1"]
    assert "expired" in capsys.readouterr().err
    assert checkpoints.CHECKPOINT.read_bytes() == before


def test_restart_archives_saved_state(finder):
    before = checkpoints.CHECKPOINT.read_bytes()
    finder.main(["--restart"])
    archives = list(Path(".").glob("backup.previous-*"))
    assert len(archives) == 1
    assert (archives[0] / "checkpoint.json").read_bytes() == before
    assert finder.count["file"] == 6


def test_atomic_write_failure_keeps_previous_checkpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checkpoints.write_checkpoint(partial_state())
    before = checkpoints.CHECKPOINT.read_bytes()

    def fail_replace(*args):
        raise OSError("synthetic replacement failure")

    monkeypatch.setattr(checkpoints.os, "replace", fail_replace)
    with pytest.raises(OSError):
        checkpoints.write_checkpoint(checkpoints.empty_checkpoint())
    assert checkpoints.CHECKPOINT.read_bytes() == before
    assert list(Path("backup").glob(".checkpoint-*")) == []


def write_legacy(state):
    Path("backup").mkdir(exist_ok=True)
    for name, value in [("hash_to_path_dict.txt", state["paths"]), ("hash_to_size_dict.txt", state["sizes"])]:
        with bz2.open(Path("backup") / name, "wb") as target:
            pickle.dump(value, target)
    for name, value in [("cursor.txt", state["cursor"] or ""), ("entries.txt", PAGE_ONE)]:
        (Path("backup") / name).write_bytes(pickle.dumps(value))


def test_legacy_resume_migrates_all_collections_without_replaying_entries(finder):
    expected = Path("duplicate_files.tsv").read_bytes()
    checkpoints.CHECKPOINT.unlink()
    write_legacy(partial_state())
    before = {name: (Path("backup") / name).read_bytes() for name in checkpoints.LEGACY_FILES}
    finder.main(["--resume-legacy"])
    assert finder.dbx.calls == [("files_list_folder_continue", "cursor-1")]
    assert finder.count["file"] == 6
    assert Path("duplicate_files.tsv").read_bytes() == expected
    for name, data in before.items():
        assert (Path("backup") / name).read_bytes() == data


def test_incomplete_legacy_set_does_not_create_checkpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_legacy(partial_state())
    (Path("backup") / "entries.txt").unlink()
    with pytest.raises(checkpoints.CheckpointError):
        checkpoints.migrate_legacy_checkpoint()
    assert not checkpoints.CHECKPOINT.exists()


def test_legacy_pickle_does_not_execute_objects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_legacy(partial_state())

    class Unsafe:
        def __reduce__(self):
            return (eval, ("__import__('pathlib').Path('executed').touch()",))

    (Path("backup") / "cursor.txt").write_bytes(pickle.dumps(Unsafe()))
    with pytest.raises(checkpoints.CheckpointError):
        checkpoints.migrate_legacy_checkpoint()
    assert not Path("executed").exists()
    assert not checkpoints.CHECKPOINT.exists()


def test_only_one_scan_can_hold_directory_lock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with checkpoints.scan_lock():
        with pytest.raises(checkpoints.CheckpointError):
            with checkpoints.scan_lock():
                pytest.fail("second lock acquired")


def test_retry_reloads_last_checkpoint_instead_of_partial_in_memory_results(finder, monkeypatch):
    checkpoints.write_checkpoint(partial_state())
    first = PAGE_TWO[:1]
    last = PAGE_TWO[1:]
    calls = []

    class FailAfterUnsavedPage(FakeDropbox):
        interrupted = False

        def files_list_folder_continue(self, cursor):
            calls.append(cursor)
            if cursor == "cursor-1":
                return dropbox.files.ListFolderResult(entries=first, cursor="cursor-mid", has_more=True)
            if not self.interrupted:
                self.interrupted = True
                raise OSError("synthetic transient failure")
            return dropbox.files.ListFolderResult(entries=last, cursor="cursor-end", has_more=False)

    monkeypatch.setattr(dropbox, "Dropbox", FailAfterUnsavedPage)
    finder.main(["--resume"])
    assert calls == ["cursor-1", "cursor-mid", "cursor-1", "cursor-mid"]
    assert finder.count["file"] == 6
    assert len(finder.hash_to_path_dict[HASH_A]) == 3


def test_legacy_completed_checkpoint_restores_count_without_listing(finder, monkeypatch):
    state = checkpoints.load_checkpoint()
    checkpoints.CHECKPOINT.unlink()
    write_legacy(state)

    class NoListing(FakeDropbox):
        def files_list_folder(self, *args, **kwargs):
            pytest.fail("completed legacy scan must not list the account")

        files_list_folder_continue = files_list_folder

    monkeypatch.setattr(dropbox, "Dropbox", NoListing)
    finder.main(["--resume-legacy"])
    assert finder.count["file"] == 6
    assert checkpoints.load_checkpoint() == state
