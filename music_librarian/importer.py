"""Import downloaded albums into the source collection."""

import os
import shutil
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import List, Optional, Tuple

from music_librarian.file_discovery import find_audio_files
from music_librarian.metadata_handler import read_metadata_from_file


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


def _audio_files(root: Path) -> List[Path]:
    """Relative paths of the audio files under `root`, excluding clutter."""
    return sorted(p for p in find_audio_files(root) if not is_clutter(p))


def read_album_identity(root: Path) -> Tuple[str, str]:
    """Read the (artist, album) shared by every audio file under `root`.

    The artist is ALBUMARTIST, falling back to ARTIST.
    """
    audio_files = _audio_files(root)
    if not audio_files:
        raise ImportFailed("no audio files found")

    artists = set()
    albums = set()
    for relative_path in audio_files:
        try:
            tags = read_metadata_from_file(str(root / relative_path))
        except Exception as e:
            raise ImportFailed(f"could not read tags from {relative_path}: {e}") from e

        artist = tags.get("albumartist") or tags.get("artist")
        album = tags.get("album")
        if not artist:
            raise ImportFailed(f"{relative_path} has no albumartist or artist tag")
        if not album:
            raise ImportFailed(f"{relative_path} has no album tag")
        artists.add(artist)
        albums.add(album)

    if len(artists) > 1:
        raise ImportFailed(f"tracks disagree on artist: {_quoted_list(artists)}")
    if len(albums) > 1:
        raise ImportFailed(f"tracks disagree on album: {_quoted_list(albums)}")

    return artists.pop(), albums.pop()


def _quoted_list(values) -> str:
    return ", ".join(repr(v) for v in sorted(values))


@dataclass
class ImportPlan:
    """A checked import, ready to run."""

    source: Path
    content_root: Path
    artist_folder: str
    album_folder: str
    new_artist: bool
    track_count: int
    other_count: int

    @property
    def relative_destination(self) -> Path:
        return Path(self.artist_folder) / self.album_folder


def _plan_import(source: Path, library_root: Path, workdir: Path) -> ImportPlan:
    content_root = unpack(source, workdir)
    artist, album = read_album_identity(content_root)

    artist_name = folder_name_for(artist)
    album_folder = folder_name_for(album)
    existing_artist = find_matching_entry(library_root, artist_name)

    if existing_artist:
        existing_album = find_matching_entry(
            library_root / existing_artist, album_folder
        )
        if existing_album:
            raise ImportFailed(
                f"{existing_artist}/{existing_album} already exists in the library"
            )

    files = [
        p.relative_to(content_root)
        for p in content_root.rglob("*")
        if p.is_file() and not is_clutter(p.relative_to(content_root))
    ]
    track_count = len(_audio_files(content_root))

    return ImportPlan(
        source=source,
        content_root=content_root,
        artist_folder=existing_artist or artist_name,
        album_folder=album_folder,
        new_artist=existing_artist is None,
        track_count=track_count,
        other_count=len(files) - track_count,
    )


def plan_imports(sources, library_root: Path, workdir: Path) -> List[ImportPlan]:
    """Check every source and plan its import, without writing to the library.

    Zips are extracted under `workdir`, which must outlive the returned plans.
    Raises ImportFailed, naming the source, at the first problem.
    """
    plans = []
    destinations = {}
    for index, source in enumerate(sources):
        source_workdir = workdir / str(index)
        source_workdir.mkdir(parents=True)
        try:
            plan = _plan_import(source, library_root, source_workdir)
        except ImportFailed as e:
            raise ImportFailed(f"{source.name}: {e}") from e

        key = _comparison_key(str(plan.relative_destination))
        if key in destinations:
            raise ImportFailed(
                f"{destinations[key].name} and {source.name} would both import "
                f"to {plan.relative_destination}"
            )
        destinations[key] = source
        plans.append(plan)

    return plans


def _ignore_clutter(directory, names):
    return [name for name in names if is_clutter(name)]


def _create_metadata_files(album_dir: Path) -> None:
    """Generate metadata.txt wherever there's audio, keeping any that exist."""
    # Imported here because the CLI module imports this one.
    from music_librarian.cli import extract_metadata_from_directory

    result = extract_metadata_from_directory(album_dir, force=False)
    if result["errors"]:
        raise ImportFailed(
            "could not generate metadata.txt: " + "; ".join(result["errors"])
        )


def run_import(
    plan: ImportPlan, library_root: Path, create_metadata: bool = True
) -> Path:
    """Copy a planned album into the library, and return where it landed.

    The album is assembled in a hidden staging directory on the same volume,
    with its metadata.txt files, then renamed into place, so it appears
    complete or not at all.
    """
    artist_dir = library_root / plan.artist_folder
    created_artist_dir = not artist_dir.exists()
    staging = Path(
        tempfile.mkdtemp(prefix=".music-librarian-import-", dir=library_root)
    )
    try:
        staged_album = staging / plan.album_folder
        shutil.copytree(plan.content_root, staged_album, ignore=_ignore_clutter)
        if create_metadata:
            _create_metadata_files(staged_album)

        artist_dir.mkdir(exist_ok=True)
        # Checked again because the library may have changed since planning,
        # and a rename onto an existing empty directory would replace it.
        existing_album = find_matching_entry(artist_dir, plan.album_folder)
        if existing_album:
            raise ImportFailed(
                f"{plan.artist_folder}/{existing_album} already exists in the library"
            )

        destination = artist_dir / plan.album_folder
        os.rename(staged_album, destination)
        return destination
    except BaseException:
        if created_artist_dir and artist_dir.is_dir() and not any(artist_dir.iterdir()):
            artist_dir.rmdir()
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
