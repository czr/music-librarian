"""Import downloaded albums into the source collection."""

import unicodedata
from pathlib import Path
from typing import Optional


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
