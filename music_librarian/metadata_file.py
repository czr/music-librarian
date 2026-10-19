"""The metadata.txt override format: parsing, generating, and applying it."""

import unicodedata

from music_librarian.metadata_handler import read_metadata_from_file


def parse_metadata_file(content):
    """Parse metadata.txt file content.

    Args:
        content: String content of metadata.txt file

    Returns:
        Dict with "album" and "files" keys containing parsed metadata
    """
    result = {"album": {}, "files": {}}
    current_file = None
    in_malformed_section = False

    for line in content.split("\n"):
        # Strip whitespace and skip empty lines and comments
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Check for file section
        if line.startswith("file:") and line.endswith(":"):
            # Valid file section
            filename = line[5:-1].strip()
            current_file = filename
            in_malformed_section = False
            if current_file not in result["files"]:
                result["files"][current_file] = {}
        elif line.startswith("file:"):
            # Malformed file section - ignore everything until next valid section
            current_file = None
            in_malformed_section = True
            continue
        else:
            # Skip metadata if we're in a malformed section
            if in_malformed_section:
                continue

            # Parse key:value pair
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()

                if current_file:
                    result["files"][current_file][key] = value
                else:
                    result["album"][key] = value

    return result


def validate_metadata_files(metadata, available_files):
    """Validate that all files referenced in metadata exist.

    Args:
        metadata: Parsed metadata dict
        available_files: List of available filenames

    Raises:
        ValueError: If a referenced file doesn't exist
    """
    # Normalize available filenames for comparison
    normalized_available = {unicodedata.normalize("NFD", f) for f in available_files}

    for filename in metadata["files"]:
        normalized_filename = unicodedata.normalize("NFD", filename)
        if normalized_filename not in normalized_available:
            raise ValueError(
                f"File '{filename}' referenced in metadata.txt does not exist"
            )


def get_normalized_file_metadata(files_metadata, filename):
    """Get file metadata with Unicode filename normalization.

    This function handles cases where the filename from the filesystem
    has different Unicode normalization than the filename in metadata.txt.

    Args:
        files_metadata: Dict mapping filenames to metadata dicts
        filename: Filename to look up (from filesystem)

    Returns:
        Dict of file metadata, or empty dict if not found
    """
    # First try direct lookup (most common case)
    if filename in files_metadata:
        return files_metadata[filename]

    # If direct lookup fails, try with normalization
    normalized_filename = unicodedata.normalize("NFD", filename)

    for key, metadata in files_metadata.items():
        if unicodedata.normalize("NFD", key) == normalized_filename:
            return metadata

    # Not found
    return {}


def merge_metadata(album_metadata, file_metadata, filename, source_file_path=None):
    """Merge source file, album, and file-specific metadata according to spec rules.

    Args:
        album_metadata: Dict of album-wide metadata
        file_metadata: Dict of file-specific metadata overrides
        filename: Name of the file being processed
        source_file_path: Path to source file for extracting existing metadata

    Returns:
        Dict of merged metadata for opusenc
    """
    result = {}

    # Start with source file metadata if available
    if source_file_path:
        try:
            source_metadata = read_metadata_from_file(source_file_path)
            if source_metadata:
                result.update(source_metadata)
        except Exception:
            # If we can't read source metadata, continue without it
            pass

    # Apply album metadata, mapping title -> album
    for key, value in album_metadata.items():
        if key == "title":
            result["album"] = value
        elif key == "artist":
            # When album artist is specified, set both artist and albumartist
            result["artist"] = value
            result["albumartist"] = value
        else:
            result[key] = value

    # Apply file-specific overrides (these completely replace any existing values)
    for key, value in file_metadata.items():
        if key == "artist" and "artist" in album_metadata:
            # When overriding artist, preserve album artist
            result["albumartist"] = album_metadata["artist"]
            result["artist"] = value
        else:
            result[key] = value

    return result


def generate_metadata_template(
    audio_files, album_metadata, file_metadata, template_only=False
):
    """Generate metadata.txt template content.

    Args:
        audio_files: List of Path objects for audio files
        album_metadata: Dict of album-wide metadata
        file_metadata: Dict mapping filenames to metadata dicts
        template_only: If True, generate empty template with no values

    Returns:
        String content for metadata.txt file
    """
    lines = []

    # Header comments
    lines.append("# This file contains metadata overrides for the export command")
    lines.append("# Fields: title, artist, date, track number, cover")
    lines.append("# Album-wide fields apply to all tracks unless overridden per-file")
    lines.append("")

    # Album metadata section
    lines.append("# Album metadata")

    if template_only:
        # Empty template
        lines.append("title:")
        lines.append("artist:")
        lines.append("date:")
        lines.append("cover:")
    else:
        # Use provided album metadata
        for key, value in album_metadata.items():
            lines.append(f"{key}: {value}")

    lines.append("")

    # Per-file metadata sections
    lines.append("# Per-file metadata")
    for audio_file in audio_files:
        filename = str(audio_file)
        lines.append(f"file: {filename}:")

        if template_only:
            # Empty template
            lines.append("title:")
            lines.append("track number:")
        else:
            # Use provided file metadata
            file_meta = file_metadata.get(filename, {})
            for key, value in file_meta.items():
                lines.append(f"{key}: {value}")

        lines.append("")

    return "\n".join(lines)
