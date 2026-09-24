"""Import the exact approved v1.2.0 archive; never execute archive contents."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile

ARCHIVE = "health_detectives_anime_v1.2.0_source.zip"
ARCHIVE_SHA256 = "2363ff73145974f757258adab32520a9441dedb3539a8bfe845c99e302c41e79"
INDEX_SHA256 = "288badb0867cfd410924687ecf64fcf780b365ea70a1b8361033b428b47e11aa"
PREFIX = "health-detectives-anime"
PENDING = b"<!-- GWAHAK_IMPORT_PENDING -->"
ROOT_FILES = {
    ".gitignore", ".nojekyll", "CHANGELOG.md", "README.md", "index.html",
    "index.template.html", "package.json", "vercel.json",
}
DIRECTORIES = {"assets", "dist", "docs", "src", "tests", "tools"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", action="store_true", help="Stage verified files in Git")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    archive = root / ARCHIVE
    if not archive.is_file():
        raise SystemExit(f"Upload {ARCHIVE} to the repository root on main first.")
    if archive.stat().st_size > 16 * 1024 * 1024:
        raise SystemExit("Archive exceeds the expected size limit.")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise SystemExit("Archive checksum mismatch. Use the original v1.2.0 source ZIP.")
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(archive) as source:
        if sum(entry.file_size for entry in source.infolist()) > 32 * 1024 * 1024:
            raise SystemExit("Expanded archive exceeds the expected size limit.")
        for entry in source.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != PREFIX:
                raise SystemExit(f"Unsafe archive path: {entry.filename}")
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise SystemExit("Archive symlinks are not allowed.")
            if entry.is_dir():
                continue
            relative = PurePosixPath(*path.parts[1:])
            name = relative.as_posix()
            if name in files or name == ".":
                raise SystemExit("Duplicate or empty archive path.")
            if not (name in ROOT_FILES or relative.parts[0] in DIRECTORIES):
                raise SystemExit(f"Unexpected project path: {name}")
            files[name] = source.read(entry)
    if len(files) != 63:
        raise SystemExit("Expected exactly 63 project files.")
    if hashlib.sha256(files.get("index.html", b"")).hexdigest() != INDEX_SHA256:
        raise SystemExit("Game HTML checksum mismatch.")
    if files.get("dist/index.html") != files["index.html"]:
        raise SystemExit("Built game copies do not match.")
    content = json.loads(files["src/content.json"])
    if content.get("version") != "1.2.0" or len(content.get("scenes", {})) != 38:
        raise SystemExit("Unexpected game version or story count.")
    # Validate every destination before replacing any file. Preserve user changes.
    for name, data in files.items():
        target = root / name
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise SystemExit(f"Unsafe destination: {name}")
        if any(parent.is_symlink() for parent in target.parents if parent != root):
            raise SystemExit(f"Symlinked destination: {name}")
        if target.exists():
            if not target.is_file():
                raise SystemExit(f"A directory occupies file path: {name}")
            previous = target.read_bytes()
            if previous != data and not (name == "README.md" and PENDING in previous):
                raise SystemExit(f"Existing edited file would be overwritten: {name}")
    for name, data in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if args.stage:
        subprocess.run(["git", "add", "--force", "--", *sorted(files)], check=True)
    print(f"Imported {len(files)} original files; v1.2.0, 38 stories, HTML checksum verified.")


if __name__ == "__main__":
    main()
