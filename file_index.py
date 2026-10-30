"""Current file state after applying ordered recursive Dropbox listing entries."""

import dropbox

import checkpoints


class FileIndex:
    def __init__(self, state):
        self.paths = {content_hash: list(paths) for content_hash, paths in state["paths"].items()}
        self.sizes = dict(state["sizes"])
        self.hash_by_path = {path: content_hash for content_hash, paths in self.paths.items() for path in paths}
        self.folders = set()
        for path in self.hash_by_path:
            self.folders.update(self.parents(path))

    @staticmethod
    def parents(path):
        parent = path.rpartition("/")[0]
        while parent:
            yield parent
            parent = parent.rpartition("/")[0]

    def remove_file(self, path):
        content_hash = self.hash_by_path.pop(path, None)
        if content_hash is None:
            return
        group = self.paths[content_hash]
        group.remove(path)
        if not group:
            del self.paths[content_hash]
            del self.sizes[content_hash]

    def remove_subtree(self, path):
        self.remove_file(path)
        if path not in self.folders and path != "":
            return
        prefix = path + "/"
        for child in list(self.hash_by_path):
            if child.startswith(prefix):
                self.remove_file(child)
        self.folders = {folder for folder in self.folders if folder != path and not folder.startswith(prefix)}

    def apply(self, entry):
        path = entry.path_lower
        root_folder = path == "" and isinstance(entry, (dropbox.files.FolderMetadata, dropbox.files.DeletedMetadata))
        if not root_folder and not checkpoints.valid_file_path(path):
            raise checkpoints.CheckpointError('cannot index Dropbox metadata "path_lower": expected a canonical absolute path; the last checkpoint is preserved')
        if isinstance(entry, dropbox.files.FileMetadata) and not entry.content_hash:
            raise checkpoints.CheckpointError('cannot index Dropbox metadata "content_hash": a content hash is required for comparison; the last checkpoint and report are preserved')
        if isinstance(entry, dropbox.files.DeletedMetadata):
            self.remove_subtree(path)
            return
        # File and folder entries also create missing parents. A parent cannot stay a file.
        for parent in self.parents(path):
            self.remove_file(parent)
            self.folders.add(parent)
        if isinstance(entry, dropbox.files.FolderMetadata):
            self.remove_file(path)
            self.folders.add(path)
        elif isinstance(entry, dropbox.files.FileMetadata):
            if self.hash_by_path.get(path) == entry.content_hash and path not in self.folders:
                self.sizes[entry.content_hash] = entry.size
                return
            self.remove_subtree(path)
            self.hash_by_path[path] = entry.content_hash
            self.paths.setdefault(entry.content_hash, []).append(path)
            self.sizes[entry.content_hash] = entry.size

    def checkpoint(self, cursor, complete):
        state = checkpoints.empty_checkpoint()
        state.update(paths=self.paths, sizes=self.sizes, count=len(self.hash_by_path),
                     cursor=cursor, complete=complete)
        return state
