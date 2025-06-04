"""File discovery functionality for the music librarian."""

from pathlib import Path
from typing import List


def find_audio_files(root_path: Path) -> List[Path]:
    """Find all FLAC and WAV audio files in a directory tree.

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

    audio_extensions = {".flac", ".wav"}
    audio_files = []

    for file_path in root_path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
            relative_path = file_path.relative_to(root_path)
            audio_files.append(relative_path)

    return audio_files
