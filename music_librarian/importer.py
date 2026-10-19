"""Import downloaded albums into the source collection."""

import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional


class ImportFailed(Exception):
    """An import can't go ahead; the message says why."""


def folder_name_for(name: str) -> str:
    """Turn a tag value into a safe folder name.

    `/` can't appear in a filename, and macOS shows `:` as `/`, so both become
    `-` (matching what Bandcamp does in its own filenames).
    """
    return name.replace("/", "-").replace(":", "-")


def _comparison_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def find_matching_entry(parent: Path, name: str) -> Optional[str]:
    """Find an entry in `parent` matching `name`, ignoring case and Unicode form.

    Returns the existing entry's name as spelled on disk, or None.
    """
    if not parent.is_dir():
        return None

    key = _comparison_key(name)
    for entry in parent.iterdir():
        if _comparison_key(entry.name) == key:
            return entry.name

    return None


def is_clutter(relative_path) -> bool:
    """Is this macOS clutter that shouldn't be imported?"""
    parts = PurePosixPath(relative_path).parts
    name = parts[-1]
    return "__MACOSX" in parts or name == ".DS_Store" or name.startswith("._")


def _content_root(directory: Path) -> Path:
    """Return the album root: `directory`, or its only subfolder if it wraps one."""
    entries = [e for e in directory.iterdir() if not is_clutter(e.name)]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return directory


def unpack(source: Path, workdir: Path) -> Path:
    """Make a source's content available as a directory, and return its root.

    A zip is extracted into `workdir`, without clutter. A directory is used in
    place; clutter in it is left for the copy step to skip.
    """
    if source.is_dir():
        return _content_root(source)

    if not (source.is_file() and source.suffix.lower() == ".zip"):
        raise ImportFailed(f"{source} is not a zip file or directory")

    try:
        with zipfile.ZipFile(source) as zf:
            for member in zf.infolist():
                if not member.is_dir() and not is_clutter(member.filename):
                    zf.extract(member, workdir)
    except zipfile.BadZipFile as e:
        raise ImportFailed(f"{source}: could not read zip ({e})") from e

    return _content_root(workdir)
