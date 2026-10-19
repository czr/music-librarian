"""File discovery functionality for the music librarian."""

from pathlib import Path
from typing import List, Dict

LOSSLESS_EXTENSIONS = {".flac", ".wav"}
LOSSY_EXTENSIONS = {".mp3", ".ogg", ".aac", ".m4a", ".opus"}
AUDIO_EXTENSIONS = LOSSLESS_EXTENSIONS | LOSSY_EXTENSIONS


def is_audio_file(file_path: Path) -> bool:
    """Is this an existing file with an audio extension?"""
    return file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTENSIONS


def find_audio_files(root_path: Path) -> List[Path]:
    """Find all audio files (lossless and lossy) in a directory tree.

    Args:
        root_path: Root directory to search from

    Returns:
        List of Path objects relative to root_path for all found audio files

    Raises:
        FileNotFoundError: If root_path does not exist
    """
    if not root_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {root_path}")

    if not root_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root_path}")

    audio_files = []

    for file_path in root_path.rglob("*"):
        if is_audio_file(file_path):
            relative_path = file_path.relative_to(root_path)
            audio_files.append(relative_path)

    return audio_files


def is_lossless_format(file_path: Path) -> bool:
    """Check if a file is in a lossless audio format.

    Args:
        file_path: Path to the audio file

    Returns:
        True if the file is in a lossless format, False otherwise
    """
    return file_path.suffix.lower() in LOSSLESS_EXTENSIONS


def find_audio_files_with_types(root_path: Path) -> Dict[str, List[Path]]:
    """Find all audio files and classify them as lossless or lossy.

    Args:
        root_path: Root directory to search from

    Returns:
        Dict with 'lossless' and 'lossy' keys containing lists of Path objects

    Raises:
        FileNotFoundError: If root_path does not exist
    """
    if not root_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {root_path}")

    if not root_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root_path}")

    result = {"lossless": [], "lossy": []}

    for file_path in root_path.rglob("*"):
        if file_path.is_file():
            suffix = file_path.suffix.lower()
            relative_path = file_path.relative_to(root_path)

            if suffix in LOSSLESS_EXTENSIONS:
                result["lossless"].append(relative_path)
            elif suffix in LOSSY_EXTENSIONS:
                result["lossy"].append(relative_path)

    return result


def find_cover_art(available_files):
    """Find cover art file in the given list of files.

    Args:
        available_files: List of filenames to search through

    Returns:
        Filename of first matching cover art file, or None if no match
    """
    # Prefixes in priority order
    cover_prefixes = ["cover", "folder", "front", "album"]
    # Supported extensions
    cover_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]

    # Search by priority order
    for prefix in cover_prefixes:
        for filename in available_files:
            filename_lower = filename.lower()
            for ext in cover_extensions:
                if filename_lower.startswith(prefix) and filename_lower.endswith(ext):
                    return filename

    return None
