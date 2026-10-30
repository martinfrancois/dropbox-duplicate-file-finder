"""Atomic scan checkpoints and explicit recovery of the old split-file format."""

from contextlib import contextmanager
import bz2
import json
import os
from pathlib import Path
import pickle
import tempfile
import uuid

if os.name == "nt":
    import msvcrt
else:
    import fcntl

DIRECTORY = Path("backup")
CHECKPOINT = DIRECTORY / "checkpoint.json"
LEGACY_FILES = ("hash_to_path_dict.txt", "hash_to_size_dict.txt", "cursor.txt", "entries.txt")


class CheckpointError(ValueError):
    """Saved state needs an explicit owner decision before scanning continues."""


def empty_checkpoint():
    return {"version": 1, "folder": "", "paths": {}, "sizes": {}, "count": 0,
            "cursor": None, "complete": False}


def valid_file_path(path):
    return (isinstance(path, str) and path.startswith("/")
            and all(part not in ("", ".", "..") for part in path.split("/")[1:]))


def validate(state):
    if not isinstance(state, dict) or set(state) != set(empty_checkpoint()):
        raise ValueError('cannot read checkpoint "fields": expected the complete version 1 field set')
    if type(state["version"]) is not int or state["version"] != 1 or state["folder"] != "":
        raise ValueError('cannot read checkpoint "version/folder": expected version 1 and the account root')
    paths, sizes = state["paths"], state["sizes"]
    if not isinstance(paths, dict) or not isinstance(sizes, dict) or paths.keys() != sizes.keys():
        raise ValueError('cannot read checkpoint "paths/sizes": expected matching content-hash keys')
    seen = set()
    for content_hash, group in paths.items():
        if not isinstance(content_hash, str) or not content_hash or not isinstance(group, list) or not group:
            raise ValueError('cannot read checkpoint "paths": expected a nonempty hash and path list')
        if type(sizes[content_hash]) is not int or sizes[content_hash] < 0:
            raise ValueError('cannot read checkpoint "sizes": expected a nonnegative integer')
        for path in group:
            if not valid_file_path(path) or path in seen:
                raise ValueError('cannot read checkpoint "paths": expected canonical absolute file paths occurring exactly once')
            seen.add(path)
    if type(state["count"]) is not int or state["count"] != len(seen):
        raise ValueError('cannot read checkpoint "count": expected the number of current paths')
    cursor, complete = state["cursor"], state["complete"]
    if type(complete) is not bool or (cursor is not None and (not isinstance(cursor, str) or not cursor)):
        raise ValueError('cannot read checkpoint "cursor/complete": expected a nonempty cursor or null and a boolean completion flag')
    if complete and cursor is not None or not complete and cursor is None and seen:
        raise ValueError('cannot read checkpoint "cursor/complete": expected a cursor for partial results and no cursor for completed results')
    return state


def load_checkpoint():
    try:
        with CHECKPOINT.open(encoding="utf-8") as source:
            return validate(json.load(source))
    except (OSError, ValueError, TypeError) as error:
        raise CheckpointError('cannot resume checkpoint "backup/checkpoint.json": preserve it for inspection or use --restart') from error


def write_checkpoint(state):
    validate(state)
    DIRECTORY.mkdir(exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=DIRECTORY)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(state, target, ensure_ascii=False)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, CHECKPOINT)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class _DataOnlyUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise ValueError('cannot read legacy checkpoint "object": expected primitive data without executable classes')


def migrate_legacy_checkpoint():
    """Read primitive data only; old entries were processed before checkpointing."""
    if CHECKPOINT.exists():
        raise CheckpointError('cannot migrate checkpoint "backup": checkpoint.json already exists; use --resume or --restart')
    try:
        if not all((DIRECTORY / name).is_file() for name in LEGACY_FILES):
            raise ValueError('cannot migrate legacy checkpoint "backup": expected all four checkpoint files')
        with bz2.open(DIRECTORY / LEGACY_FILES[0], "rb") as source:
            paths = _DataOnlyUnpickler(source).load()
        with bz2.open(DIRECTORY / LEGACY_FILES[1], "rb") as source:
            sizes = _DataOnlyUnpickler(source).load()
        with (DIRECTORY / "cursor.txt").open("rb") as source:
            cursor = _DataOnlyUnpickler(source).load()
        if not isinstance(cursor, str):
            raise ValueError('cannot migrate legacy checkpoint "cursor.txt": expected a string')
        state = empty_checkpoint()
        state.update(paths=paths, sizes=sizes, count=sum(len(group) for group in paths.values()),
                     cursor=cursor or None, complete=cursor == "")
        validate(state)
    except (OSError, ValueError, TypeError, AttributeError, EOFError, pickle.UnpicklingError) as error:
        raise CheckpointError('cannot migrate checkpoint "backup": need a complete, consistent legacy set; preserve it or use --restart') from error
    # Keep all legacy files. entries.txt is deliberately never unpickled or replayed.
    write_checkpoint(state)


def prepare_run(*, resume=False, restart=False, resume_legacy=False):
    if restart and DIRECTORY.exists():
        archived = DIRECTORY.with_name("backup.previous-" + uuid.uuid4().hex)
        DIRECTORY.rename(archived)
        print(f"Previous state preserved in {archived}")
    if resume_legacy:
        migrate_legacy_checkpoint()
    elif resume:
        load_checkpoint()
    elif not restart and DIRECTORY.exists() and any(DIRECTORY.iterdir()):
        raise CheckpointError('cannot start scan "backup": saved files exist; use --resume, --resume-legacy, or --restart')
    DIRECTORY.mkdir(exist_ok=True)


@contextmanager
def scan_lock():
    # Keep the inode in place so two processes cannot acquire different lock files.
    with open(".finder.lock", "a+b") as lock:
        if os.name == "nt":
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
        try:
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError) as error:
            raise CheckpointError('cannot start scan ".finder.lock": another finder is running in this directory') from error
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)
