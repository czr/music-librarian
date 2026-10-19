"""Audio processing functionality for transcoding and copying files."""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from .metadata_handler import apply_metadata_to_file


def copy_with_metadata(
    source_path: str, dest_path: str, metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Copy a lossy audio file and apply metadata overrides.

    Args:
        source_path: Path to source audio file
        dest_path: Path to destination audio file
        metadata: Optional metadata to apply after copying

    Raises:
        IOError: If copy operation fails
        ValueError: If metadata application fails
    """
    # Ensure destination directory exists
    dest_dir = os.path.dirname(dest_path)
    os.makedirs(dest_dir, exist_ok=True)

    # Copy the file
    shutil.copy2(source_path, dest_path)

    # Apply metadata if provided
    if metadata:
        apply_metadata_to_file(dest_path, metadata)


def get_output_filename(input_filename: str, file_type: str) -> str:
    """Get the appropriate output filename based on file type.

    Args:
        input_filename: Original filename
        file_type: Either 'lossless' or 'lossy'

    Returns:
        Output filename with appropriate extension
    """
    input_path = Path(input_filename)

    if file_type == "lossless":
        # Lossless files get transcoded to .opus
        return str(input_path.with_suffix(".opus"))
    else:
        # Lossy files preserve their original extension
        return str(input_path)


def build_opusenc_command(input_file, output_file, quality=None, metadata=None):
    """Build opusenc command with optional quality and metadata.

    Args:
        input_file: Path to input audio file
        output_file: Path to output .opus file
        quality: Optional bitrate for encoding
        metadata: Optional dict of metadata tags

    Returns:
        List of command arguments for subprocess
    """
    cmd = ["opusenc"]

    # Add quality setting if specified
    if quality:
        cmd.extend(["--bitrate", str(quality)])

    # Discard existing metadata from source file to ensure clean replacement
    cmd.append("--discard-comments")

    # Add metadata using specific opusenc options
    if metadata:
        for key, value in metadata.items():
            # Skip empty values and cover field
            if not value or key == "cover":
                continue

            # Use specific opusenc options for known fields
            if key == "title":
                cmd.extend(["--title", value])
            elif key == "artist":
                cmd.extend(["--artist", value])
            elif key == "album":
                cmd.extend(["--album", value])
            elif key == "date":
                cmd.extend(["--date", value])
            elif key == "track number":
                cmd.extend(["--tracknumber", value])
            elif key == "albumartist":
                # Use comment for albumartist since there's no specific option
                cmd.extend(["--comment", f"ALBUMARTIST={value}"])
            else:
                # Fall back to comment for other fields
                opus_key = key.upper().replace(" ", "")
                cmd.extend(["--comment", f"{opus_key}={value}"])

    cmd.extend([input_file, output_file])
    return cmd
