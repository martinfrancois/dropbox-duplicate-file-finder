import csv

from pathlib import Path

import reformat
import reformat_rclone

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

GIB = 1024**3
# Sizes of the two duplicated files in examples/duplicate_files.tsv.
IMAGE_SIZE = 2048
REPORT_SIZE = 512


def folder_line(folder, file_size, copies):
    # Every folder in the example holds one duplicated file, so its line counts that file once.
    return f"{folder}§1§{copies}§{file_size / GIB} GB§{copies * file_size / GIB} GB"


def test_reformat_groups_duplicates_by_folder(tmp_path):
    output = tmp_path / "formatted.txt"
    summary = tmp_path / "summary.txt"

    reformat.process_duplicate_files(str(EXAMPLES / "duplicate_files.tsv"), str(output), str(summary))

    header = (
        "path to folder§amount of duplicate files in folder§duplicate file count including all "
        "duplicate copies§folder size of duplicate files§folder size including all duplicate copies"
    )
    archive = folder_line("/archive", REPORT_SIZE, copies=2)
    backup = folder_line("/backup", IMAGE_SIZE, copies=3)
    documents = folder_line("/documents", REPORT_SIZE, copies=2)
    photos = folder_line("/photos", IMAGE_SIZE, copies=3)
    photos_2024 = folder_line("/photos/2024", IMAGE_SIZE, copies=3)
    assert output.read_text().splitlines() == [
        header,
        archive,
        "report.pdf§/documents/report.pdf",
        "---",
        backup,
        "img_0001.jpg§/photos/2024/img_0001.jpg§/photos/img_0001.jpg",
        "---",
        documents,
        "report.pdf§/archive/report.pdf",
        "---",
        photos,
        "img_0001.jpg§/backup/img_0001.jpg§/photos/2024/img_0001.jpg",
        "---",
        photos_2024,
        "img_0001.jpg§/backup/img_0001.jpg§/photos/img_0001.jpg",
        "---",
    ]
    assert summary.read_text().splitlines() == [header, archive, backup, documents, photos, photos_2024]


def test_reformat_rclone_groups_duplicates_by_folder(tmp_path):
    output = tmp_path / "formatted.txt"

    reformat_rclone.process_duplicate_files(str(EXAMPLES / "rclone-duplicates.txt"), str(output))

    assert output.read_text().splitlines() == [
        "/",
        "notes.txt§documents/notes.txt",
        "---",
        "backup",
        "img_0001.jpg§photos/2024/img_0001.jpg§photos/img_0001.jpg",
        "---",
        "documents",
        "notes.txt§notes.txt",
        "---",
        "photos",
        "img_0001.jpg§backup/img_0001.jpg§photos/2024/img_0001.jpg",
        "---",
        "photos/2024",
        "img_0001.jpg§backup/img_0001.jpg§photos/img_0001.jpg",
        "---",
    ]


def test_section_separator_quotes_and_newlines_round_trip_from_tsv(tmp_path):
    paths = ['/folder§name/a"§file.txt', '/other/a"§file.txt', '/line\nbreak\rreturn/a"§file.txt']
    source = tmp_path / "input.tsv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["Hash", "Size", "Paths"])
        writer.writerow(["same-hash", 12, *paths])
    output, summary = tmp_path / "formatted.txt", tmp_path / "summary.txt"
    reformat.process_duplicate_files(source, output, summary)
    with summary.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream, delimiter="§"))
    assert all(len(row) == 5 for row in rows)
    assert [row[0] for row in rows[1:]] == ['/folder§name', '/line\nbreak\rreturn', '/other']
    with output.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream, delimiter="§"))
    for block, path in enumerate(sorted(paths)):
        assert rows[1 + block * 3][0] == path.rsplit('/', 1)[0]
        assert rows[2 + block * 3] == ['a"§file.txt', *sorted(other for other in paths if other != path)]
        assert rows[3 + block * 3] == ["---"]


def test_rclone_quotes_separators_and_keeps_path_whitespace(tmp_path):
    paths = ['folder§name/a"§file.txt ', 'other/a"§file.txt ', 'third/a"§file.txt ']
    source = tmp_path / "rclone.txt"
    source.write_text(''.join(f'hash  {path}\n' for path in paths), encoding="utf-8")
    output = tmp_path / "formatted.txt"
    reformat_rclone.process_duplicate_files(source, output)
    with output.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream, delimiter="§"))
    for block, path in enumerate(paths):
        assert rows[block * 3] == [path.rsplit('/', 1)[0]]
        assert rows[1 + block * 3] == ['a"§file.txt ', *sorted(other for other in paths if other != path)]
        assert rows[2 + block * 3] == ["---"]


def test_rclone_singleton_separator_name_is_not_a_block_terminator(tmp_path):
    source = tmp_path / "rclone.txt"
    source.write_text("hash  folder/---\n")
    output = tmp_path / "formatted.txt"
    reformat_rclone.process_duplicate_files(source, output)
    with output.open(newline="") as stream:
        assert list(csv.reader(stream, delimiter="§")) == [["folder"], ["---", ""], ["---"]]


def test_summary_counts_each_copy_once_across_same_folder_content(tmp_path):
    source = tmp_path / "input.tsv"
    source.write_text(
        "Hash\tSize\tPaths\n"
        "a\t12\t/a/first\t/a/second\t/b/third\n"
        "b\t7\t/a/different\t/b/copy\n"
    )
    output, summary = tmp_path / "full", tmp_path / "summary"
    reformat.process_duplicate_files(source, output, summary)
    with summary.open(newline="") as stream:
        rows = list(csv.reader(stream, delimiter="§"))
    assert rows[1:] == [
        ["/a", "3", "5", f"{31 / GIB} GB", f"{50 / GIB} GB"],
        ["/b", "2", "5", f"{19 / GIB} GB", f"{50 / GIB} GB"],
    ]
    with output.open(newline="") as stream:
        detailed = list(csv.reader(stream, delimiter="§"))
    assert rows[1] in detailed and rows[2] in detailed


def test_summary_same_folder_pair_does_not_multiply_copies(tmp_path):
    source = tmp_path / "input.tsv"
    source.write_text("Hash\tSize\tPaths\nh\t12\t/a/one\t/a/two\n")
    output, summary = tmp_path / "full", tmp_path / "summary"
    reformat.process_duplicate_files(source, output, summary)
    with summary.open(newline="") as stream:
        assert list(csv.reader(stream, delimiter="§"))[1] == [
            "/a", "2", "2", f"{24 / GIB} GB", f"{24 / GIB} GB"
        ]


def test_absolute_root_paths_have_root_folder_labels(tmp_path):
    source, output, summary = [tmp_path / name for name in ("input", "full", "summary")]
    source.write_text("Hash\tSize\tPaths\nh\t12\t/root§name.txt\t/dir/copy.txt\n")
    reformat.process_duplicate_files(source, output, summary)
    with summary.open(newline="") as stream:
        rows = list(csv.reader(stream, delimiter="§"))
    assert [row[0] for row in rows[1:]] == ["/", "/dir"]
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream, delimiter="§"))
    assert rows[2] == ["root§name.txt", "/dir/copy.txt"]
    source.write_text("h  /root§name.txt\nh  /dir/copy.txt\n")
    reformat_rclone.process_duplicate_files(source, output)
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream, delimiter="§"))
    assert rows == [
        ["/"], ["root§name.txt", "/dir/copy.txt"], ["---"],
        ["/dir"], ["copy.txt", "/root§name.txt"], ["---"],
    ]


def test_relative_root_paths_keep_filename(tmp_path):
    source, output, summary = [tmp_path / name for name in ("input", "full", "summary")]
    source.write_text("Hash\tSize\tPaths\nh\t12\troot.txt\tdir/copy.txt\n")
    reformat.process_duplicate_files(source, output, summary)
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream, delimiter="§"))
    assert rows[1][0] == "/"
    assert rows[2] == ["root.txt", "dir/copy.txt"]
