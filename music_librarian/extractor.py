"""Generate metadata.txt files from the tags in existing audio files."""

from pathlib import Path

from music_librarian.file_discovery import find_cover_art, is_audio_file
from music_librarian.metadata_file import generate_metadata_template
from music_librarian.metadata_handler import read_metadata_from_file


def extract_metadata_from_file(filepath):
    """Extract metadata from a single audio file.

    Args:
        filepath: Path to audio file

    Returns:
        Dict containing metadata fields
    """
    try:
        metadata = read_metadata_from_file(filepath)
        # Ensure all expected fields are present
        result = {
            "title": metadata.get("title", ""),
            "artist": metadata.get("artist", ""),
            "albumartist": metadata.get("albumartist", ""),
            "album": metadata.get("album", ""),
            "date": metadata.get("date", ""),
            "track number": metadata.get("track number", ""),
        }
        return result
    except Exception:
        # If metadata extraction fails, return empty metadata
        return {
            "title": "",
            "artist": "",
            "albumartist": "",
            "album": "",
            "date": "",
            "track number": "",
        }


def find_album_directories(root_directory):
    """Find all directories that contain audio files directly (not in subdirectories).

    Args:
        root_directory: Path to root directory to search

    Returns:
        List of Path objects for directories containing audio files
    """
    root_path = Path(root_directory)
    album_directories = []

    # Check all directories recursively
    for directory_path in [root_path] + list(root_path.rglob("*")):
        if not directory_path.is_dir():
            continue

        # Check if this directory contains audio files directly (not in subdirectories)
        if any(is_audio_file(p) for p in directory_path.iterdir()):
            album_directories.append(directory_path)

    return album_directories


def discover_and_sort_audio_files(directory):
    """Discover audio files only in the specified directory (not recursively).

    Args:
        directory: Path to directory to search

    Returns:
        List of Path objects for audio files in the directory only (not subdirectories)
    """
    directory_path = Path(directory)
    return sorted(Path(p.name) for p in directory_path.iterdir() if is_audio_file(p))


def extract_metadata_from_single_directory(directory, force=False, template_only=False):
    """Extract metadata from audio files in a single directory and generate metadata.txt.

    Args:
        directory: Path to directory to process
        force: Whether to overwrite existing metadata.txt files
        template_only: Whether to generate empty template

    Returns:
        Dict with processing results for this single directory
    """
    directory_path = Path(directory)
    metadata_file = directory_path / "metadata.txt"

    # Check if metadata.txt already exists
    if metadata_file.exists() and not force:
        return {"processed": 0, "skipped": 1, "errors": []}

    # Discover and sort audio files (only in this directory, not recursively)
    try:
        audio_files = discover_and_sort_audio_files(directory)
    except Exception as e:
        return {
            "processed": 0,
            "skipped": 0,
            "errors": [f"Failed to discover audio files: {str(e)}"],
        }

    if not audio_files:
        return {
            "processed": 0,
            "skipped": 0,
            "errors": [f"No audio files found in directory {directory}"],
        }

    # Extract metadata from files
    album_metadata = {}
    file_metadata = {}

    if not template_only:
        # Extract album metadata from first file
        first_file = directory_path / audio_files[0]
        try:
            first_file_meta = extract_metadata_from_file(str(first_file))
            # Map to album metadata (title becomes album title, etc.)
            # Export applies the album artist to every track's ARTIST, so
            # differing track artists are written per file below.
            album_metadata = {
                "title": first_file_meta.get("album", ""),
                "artist": first_file_meta.get("albumartist")
                or first_file_meta.get("artist", ""),
                "date": first_file_meta.get("date", ""),
            }
        except Exception as e:
            return {
                "processed": 0,
                "skipped": 0,
                "errors": [
                    f"Failed to extract metadata from {audio_files[0]}: {str(e)}"
                ],
            }

        # Detect cover art in the directory
        try:
            all_files_in_dir = [f.name for f in directory_path.iterdir() if f.is_file()]
            cover_file = find_cover_art(all_files_in_dir)
            album_metadata["cover"] = cover_file if cover_file else ""
        except Exception:
            # If cover detection fails, just set empty cover
            album_metadata["cover"] = ""

        # Extract metadata for each file
        for audio_file in audio_files:
            filepath = directory_path / audio_file
            try:
                meta = extract_metadata_from_file(str(filepath))
                file_metadata[str(audio_file)] = {"title": meta.get("title", "")}
                track_artist = meta.get("artist", "")
                if track_artist and track_artist != album_metadata["artist"]:
                    file_metadata[str(audio_file)]["artist"] = track_artist
                file_metadata[str(audio_file)]["track number"] = meta.get(
                    "track number", ""
                )
            except Exception as e:
                return {
                    "processed": 0,
                    "skipped": 0,
                    "errors": [
                        f"Failed to extract metadata from {audio_file}: {str(e)}"
                    ],
                }

    # Generate template content
    try:
        template_content = generate_metadata_template(
            audio_files, album_metadata, file_metadata, template_only
        )
    except Exception as e:
        return {
            "processed": 0,
            "skipped": 0,
            "errors": [f"Failed to generate template: {str(e)}"],
        }

    # Write metadata.txt file
    try:
        metadata_file.write_text(template_content, encoding="utf-8")
    except Exception as e:
        return {
            "processed": 0,
            "skipped": 0,
            "errors": [f"Failed to write metadata.txt: {str(e)}"],
        }

    return {"processed": 1, "skipped": 0, "errors": []}


def extract_metadata_from_directory(directory, force=False, template_only=False):
    """Extract metadata from all album directories found recursively.

    Args:
        directory: Path to root directory to search for album directories
        force: Whether to overwrite existing metadata.txt files
        template_only: Whether to generate empty template

    Returns:
        Dict with aggregated processing results
    """
    # Find all directories that contain audio files directly
    try:
        album_directories = find_album_directories(directory)
    except Exception as e:
        return {
            "processed": 0,
            "skipped": 0,
            "errors": [f"Failed to find album directories: {str(e)}"],
        }

    if not album_directories:
        raise ValueError("No audio files found in directory")

    # Process each album directory
    total_processed = 0
    total_skipped = 0
    total_errors = []

    for album_dir in album_directories:
        result = extract_metadata_from_single_directory(
            album_dir, force=force, template_only=template_only
        )
        total_processed += result.get("processed", 0)
        total_skipped += result.get("skipped", 0)
        total_errors.extend(result.get("errors", []))

    return {
        "processed": total_processed,
        "skipped": total_skipped,
        "errors": total_errors,
    }
