"""File discovery functionality for the music librarian."""

from pathlib import Path
from typing import List, Dict


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

    # Include both lossless and lossy audio formats
    audio_extensions = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".opus"}
    audio_files = []

    for file_path in root_path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
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
    lossless_extensions = {".flac", ".wav"}
    return file_path.suffix.lower() in lossless_extensions


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

    lossless_extensions = {".flac", ".wav"}
    lossy_extensions = {".mp3", ".ogg", ".aac", ".m4a", ".opus"}

    result = {"lossless": [], "lossy": []}

    for file_path in root_path.rglob("*"):
        if file_path.is_file():
            suffix = file_path.suffix.lower()
            relative_path = file_path.relative_to(root_path)

            if suffix in lossless_extensions:
                result["lossless"].append(relative_path)
            elif suffix in lossy_extensions:
                result["lossy"].append(relative_path)

    return result
