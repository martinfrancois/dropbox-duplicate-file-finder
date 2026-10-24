from pathlib import Path

import reformat
import reformat_rclone

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def test_reformat_groups_duplicates_by_folder(tmp_path):
    output = tmp_path / "formatted.txt"
    summary = tmp_path / "summary.txt"

    reformat.process_duplicate_files(str(EXAMPLES / "duplicate_files.tsv"), str(output), str(summary))

    header = (
        "path to folder§amount of duplicate files in folder§duplicate file count including all "
        "duplicate copies§folder size of duplicate files§folder size including all duplicate copies"
    )
    gib = 1024**3
    archive = f"/archive§1§1§{512 / gib} GB§{512 / gib} GB"
    backup = f"/backup§1§2§{2048 / gib} GB§{2 * 2048 / gib} GB"
    documents = f"/documents§1§1§{512 / gib} GB§{512 / gib} GB"
    photos = f"/photos§1§2§{2048 / gib} GB§{2 * 2048 / gib} GB"
    photos_2024 = f"/photos/2024§1§2§{2048 / gib} GB§{2 * 2048 / gib} GB"
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
