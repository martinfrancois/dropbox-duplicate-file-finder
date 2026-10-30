import importlib.util
import os
from pathlib import Path
import runpy
import socket
from unittest.mock import patch

import dropbox
import dotenv


ROOT = Path(__file__).resolve().parent.parent


def test_import_has_no_credentials_network_or_output_side_effects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("DROPBOX_"):
            monkeypatch.delenv(key)
    spec = importlib.util.spec_from_file_location("import_probe", ROOT / "find_duplicates.py")
    module = importlib.util.module_from_spec(spec)
    with patch.object(dotenv, "load_dotenv", side_effect=AssertionError("credential loading during import")), \
         patch.object(dropbox, "Dropbox", side_effect=AssertionError("client creation during import")), \
         patch.object(socket.socket, "connect", side_effect=AssertionError("network during import")), \
         patch.object(Path, "open", side_effect=AssertionError("file access during import")), \
         patch("builtins.open", side_effect=AssertionError("file access during import")), \
         patch("os.makedirs", side_effect=AssertionError("directory creation during import")):
        spec.loader.exec_module(module)
    assert list(tmp_path.iterdir()) == []


def test_explicit_cli_still_runs_finder(tmp_path, monkeypatch):
    from test_finder import FakeDropbox
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DROPBOX_OAUTH2_ACCESS_TOKEN_EXPIRATION", "2030-01-01T00:00:00")
    monkeypatch.setattr(dropbox, "Dropbox", FakeDropbox)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: False)
    runpy.run_path(str(ROOT / "find_duplicates.py"), run_name="__main__")
    assert (tmp_path / "duplicate_files.tsv").read_text().count("\n") == 3
