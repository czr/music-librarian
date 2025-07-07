import os
import sys
import subprocess
import shutil
from pathlib import Path
import click


@click.group()
@click.version_option()
def cli():
    "Music Librarian is CZR's opinionated music manager."


@cli.command(name="export")
@click.argument("source_directories", nargs=-1, required=True)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Overwrite existing files in destination",
)
def export(source_directories, force):
    """Export audio files from source collection to destination collection."""
    # Validate environment variables
    source_root = os.environ.get("MUSIC_SOURCE_ROOT")
    dest_root = os.environ.get("MUSIC_DEST_ROOT")

    if not source_root or source_root.strip() == "":
        click.echo("Error: MUSIC_SOURCE_ROOT environment variable not set", err=True)
        sys.exit(1)

    if not dest_root or dest_root.strip() == "":
        click.echo("Error: MUSIC_DEST_ROOT environment variable not set", err=True)
        sys.exit(1)

    # Validate that source directories are under MUSIC_SOURCE_ROOT
    for source_dir in source_directories:
        abs_source = os.path.abspath(source_dir)
        abs_source_root = os.path.abspath(source_root)

        if not abs_source.startswith(abs_source_root):
            click.echo(
                f"Error: {source_dir} is not under MUSIC_SOURCE_ROOT ({source_root})",
                err=True,
            )
            sys.exit(1)

    click.echo(f"Exporting {len(source_directories)} directories...")
    click.echo(f"Source root: {source_root}")
    click.echo(f"Destination root: {dest_root}")
    click.echo(f"Force overwrite: {force}")

    # Process each source directory
    total_processed = 0
    total_skipped = 0
    total_errors = []

    for source_dir in source_directories:
        click.echo(f"\nProcessing: {source_dir}")

        # Resolve destination directory
        dest_dir = resolve_destination_path(source_dir, source_root, dest_root)

        try:
            result = process_directory(source_dir, dest_dir, force=force)

            total_processed += result["processed"]
            total_skipped += result["skipped"]
            total_errors.extend(result["errors"])

            click.echo(f"  Processed: {result['processed']} files")
            click.echo(f"  Skipped: {result['skipped']} files")
            if result["cover_art_copied"]:
                click.echo(f"  Cover art copied")

            if result["errors"]:
                for error in result["errors"]:
                    click.echo(f"  Error: {error}", err=True)

        except Exception as e:
            error_msg = f"Failed to process directory {source_dir}: {str(e)}"
            total_errors.append(error_msg)
            click.echo(f"  Error: {error_msg}", err=True)

    # Summary
    click.echo(f"\nSummary:")
    click.echo(f"  Total processed: {total_processed}")
    click.echo(f"  Total skipped: {total_skipped}")
    click.echo(f"  Total errors: {len(total_errors)}")

    # Exit with error code if there were errors
    if total_errors:
        sys.exit(1)


@cli.command(name="extract-metadata")
@click.argument("source_directories", nargs=-1, required=True)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Overwrite existing metadata.txt files",
)
@click.option(
    "--template-only",
    is_flag=True,
    help="Generate empty template with field names but no values from audio files",
)
def extract_metadata(source_directories, force, template_only):
    """Generate metadata.txt files from audio files in specified directories."""
    click.echo(f"Extracting metadata from {len(source_directories)} directories...")
    click.echo(f"Force overwrite: {force}")
    click.echo(f"Template only: {template_only}")

    # Process each source directory
    total_processed = 0
    total_skipped = 0
    total_errors = []

    for source_dir in source_directories:
        click.echo(f"\nProcessing: {source_dir}")

        try:
            result = extract_metadata_from_directory(
                source_dir, force=force, template_only=template_only
            )

            total_processed += result.get("processed", 0)
            total_skipped += result.get("skipped", 0)
            total_errors.extend(result.get("errors", []))

            click.echo(f"  Processed: {result.get('processed', 0)} directories")
            click.echo(f"  Skipped: {result.get('skipped', 0)} directories")

            if result.get("errors"):
                for error in result["errors"]:
                    click.echo(f"  Error: {error}", err=True)

        except Exception as e:
            error_msg = f"Failed to process directory {source_dir}: {str(e)}"
            total_errors.append(error_msg)
            click.echo(f"  Error: {error_msg}", err=True)

    # Summary
    click.echo(f"\nSummary:")
    click.echo(f"  Total processed: {total_processed}")
    click.echo(f"  Total skipped: {total_skipped}")
    click.echo(f"  Total errors: {len(total_errors)}")

    # Exit with error code if there were errors
    if total_errors:
        sys.exit(1)


def resolve_destination_path(source_dir, source_root, dest_root):
    """Resolve destination path from source directory path.

    Args:
        source_dir: Absolute path to source directory
        source_root: Absolute path to source root directory
        dest_root: Absolute path to destination root directory

    Returns:
        Absolute path to corresponding destination directory
    """
    source_path = Path(source_dir)
    source_root_path = Path(source_root)
    dest_root_path = Path(dest_root)

    # Get relative path from source root to source directory
    relative_path = source_path.relative_to(source_root_path)

    # Append to destination root
    dest_path = dest_root_path / relative_path

    return str(dest_path)


def resolve_output_filename(input_filename):
    """Convert input filename to output .opus filename.

    Args:
        input_filename: Input filename (with .flac or .wav extension)

    Returns:
        Output filename with .opus extension
    """
    input_path = Path(input_filename)
    return str(input_path.with_suffix(".opus"))


def resolve_output_filename_for_type(input_filename, file_type):
    """Convert input filename to appropriate output filename based on type.

    Args:
        input_filename: Input filename
        file_type: Either 'lossless' or 'lossy'

    Returns:
        Output filename with appropriate extension
    """
    from music_librarian.audio_processor import get_output_filename

    return get_output_filename(input_filename, file_type)


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
    for filename in metadata["files"]:
        if filename not in available_files:
            raise ValueError(
                f"File '{filename}' referenced in metadata.txt does not exist"
            )


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


def check_external_tools():
    """Check that required external tools are available.

    Raises:
        SystemExit: If any required tool is missing
    """
    tools = ["opusenc", "rsgain"]

    for tool in tools:
        if not shutil.which(tool):
            click.echo(f"Error: {tool} not found in PATH", err=True)
            sys.exit(1)


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

    # Add metadata comments if specified
    if metadata:
        for key, value in metadata.items():
            # Convert metadata key to opus comment format
            comment_key = key.upper().replace(" ", "")
            # Handle special cases
            if comment_key == "TRACKNUMBER":
                comment_key = "TRACKNUMBER"
            elif key == "title" and "album" in metadata:
                # Track title vs album title
                comment_key = "TITLE"
            elif key == "title":
                # Album title
                comment_key = "ALBUM" if key == "title" else "TITLE"

            # Map common fields
            field_mapping = {
                "TITLE": "TITLE",
                "ARTIST": "ARTIST",
                "ALBUM": "ALBUM",
                "DATE": "DATE",
                "TRACKNUMBER": "TRACKNUMBER",
                "ALBUMARTIST": "ALBUMARTIST",
            }

            # Use direct key mapping for known fields
            if key == "title":
                opus_key = "TITLE"
            elif key == "artist":
                opus_key = "ARTIST"
            elif key == "album":
                opus_key = "ALBUM"
            elif key == "date":
                opus_key = "DATE"
            elif key == "track number":
                opus_key = "TRACKNUMBER"
            elif key == "albumartist":
                opus_key = "ALBUMARTIST"
            elif key == "cover":
                # Skip cover field - it's for file operations, not audio metadata
                continue
            else:
                opus_key = key.upper().replace(" ", "")

            cmd.extend(["--comment", f"{opus_key}={value}"])

    cmd.extend([input_file, output_file])
    return cmd


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
        from music_librarian.metadata_handler import read_metadata_from_file

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


def build_rsgain_command(directory):
    """Build rsgain command for ReplayGain processing.

    Args:
        directory: Path to directory containing .opus files

    Returns:
        List of command arguments for subprocess
    """
    return ["rsgain", "easy", directory]


def build_rsgain_command_for_mixed_formats(directory):
    """Build rsgain command for ReplayGain processing of mixed audio formats.

    Args:
        directory: Path to directory containing mixed audio files

    Returns:
        List of command arguments for subprocess
    """
    # rsgain can handle mixed formats in the same directory
    return ["rsgain", "easy", directory]


def get_opus_quality():
    """Get Opus quality setting from environment or default.

    Returns:
        String quality setting for opusenc
    """
    return os.environ.get("OPUS_QUALITY", "128")


def process_directory(source_dir, dest_dir, force=False):
    """Process a single directory for mixed audio formats (transcoding and copying).

    Args:
        source_dir: Path to source directory
        dest_dir: Path to destination directory
        force: Whether to overwrite existing files

    Returns:
        Dict with processing results and statistics
    """
    from music_librarian.file_discovery import (
        find_audio_files_with_types,
        is_lossless_format,
    )
    from music_librarian.audio_processor import process_audio_file

    # Check external tools are available
    check_external_tools()

    # Get quality setting
    quality = get_opus_quality()

    # Create destination directory
    os.makedirs(dest_dir, exist_ok=True)

    # Find all audio files with type classification
    audio_files_by_type = find_audio_files_with_types(Path(source_dir))
    all_audio_files = audio_files_by_type["lossless"] + audio_files_by_type["lossy"]

    if not all_audio_files:
        return {"processed": 0, "skipped": 0, "errors": [], "cover_art_copied": False}

    # Look for metadata.txt
    metadata_file = os.path.join(source_dir, "metadata.txt")
    metadata = {"album": {}, "files": {}}

    if os.path.exists(metadata_file):
        with open(metadata_file, "r", encoding="utf-8") as f:
            content = f.read()
        metadata = parse_metadata_file(content)

        # Validate that referenced files exist
        available_filenames = [str(f) for f in all_audio_files]
        validate_metadata_files(metadata, available_filenames)

    # Process each audio file
    processed = 0
    skipped = 0
    errors = []

    for audio_file in all_audio_files:
        try:
            # Determine file type
            file_type = "lossless" if is_lossless_format(audio_file) else "lossy"

            # Build paths preserving relative directory structure
            input_path = os.path.join(source_dir, audio_file)
            output_filename = resolve_output_filename_for_type(
                str(audio_file), file_type
            )
            output_path = os.path.join(dest_dir, output_filename)

            # Create subdirectories in destination if needed
            output_dir = os.path.dirname(output_path)
            if output_dir != dest_dir:
                os.makedirs(output_dir, exist_ok=True)

            # Skip if exists and not forcing
            if os.path.exists(output_path) and not force:
                skipped += 1
                continue

            # Merge metadata for this file
            file_metadata = metadata["files"].get(str(audio_file), {})
            merged_metadata = merge_metadata(
                metadata["album"], file_metadata, str(audio_file), input_path
            )

            # Process the file (transcode or copy based on type)
            if file_type == "lossless":
                # Transcode lossless files to Opus
                cmd = build_opusenc_command(
                    input_path, output_path, quality=quality, metadata=merged_metadata
                )
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                # Copy lossy files and apply metadata
                from music_librarian.audio_processor import copy_with_metadata

                copy_with_metadata(input_path, output_path, merged_metadata)

            processed += 1

        except Exception as e:
            errors.append(f"Error processing {audio_file}: {str(e)}")

    # Copy cover art if present - check for metadata specification first
    cover_art_copied = False

    # Check if cover is specified in metadata.txt
    specified_cover = metadata["album"].get("cover", "").strip()

    if specified_cover:
        # Use cover specified in metadata.txt
        try:
            cover_src = os.path.join(source_dir, specified_cover)
            if os.path.exists(cover_src):
                # Extract extension and create cover.{ext} filename
                _, ext = os.path.splitext(specified_cover)
                cover_dest = os.path.join(dest_dir, f"cover{ext}")

                if not os.path.exists(cover_dest) or force:
                    shutil.copy2(cover_src, cover_dest)
                    cover_art_copied = True
            else:
                errors.append(
                    f"Cover file specified in metadata.txt not found: {specified_cover}"
                )
        except Exception as e:
            errors.append(
                f"Error copying specified cover art {specified_cover}: {str(e)}"
            )
    else:
        # Fall back to automatic cover art detection
        # Get unique directories that contain audio files
        audio_dirs = set()
        for audio_file in all_audio_files:
            audio_dir = os.path.dirname(str(audio_file))
            if audio_dir:  # Only add if there's a subdirectory
                audio_dirs.add(audio_dir)
            else:  # Files in root directory
                audio_dirs.add("")

        # Check each directory for cover art
        for audio_dir in audio_dirs:
            source_subdir = (
                os.path.join(source_dir, audio_dir) if audio_dir else source_dir
            )
            dest_subdir = os.path.join(dest_dir, audio_dir) if audio_dir else dest_dir

            if os.path.exists(source_subdir):
                all_files = os.listdir(source_subdir)
                cover_art = find_cover_art(all_files)

                if cover_art:
                    try:
                        cover_src = os.path.join(source_subdir, cover_art)
                        cover_dest = os.path.join(dest_subdir, cover_art)

                        # Ensure destination subdirectory exists
                        os.makedirs(dest_subdir, exist_ok=True)

                        if not os.path.exists(cover_dest) or force:
                            # Actually copy the cover art
                            shutil.copy2(cover_src, cover_dest)
                            cover_art_copied = True
                    except Exception as e:
                        errors.append(
                            f"Error copying cover art from {audio_dir}: {str(e)}"
                        )

    # Run ReplayGain processing if files were processed
    if processed > 0:
        try:
            rsgain_cmd = build_rsgain_command_for_mixed_formats(dest_dir)
            # Actually run rsgain
            subprocess.run(rsgain_cmd, check=True, capture_output=True)
        except Exception as e:
            errors.append(f"Error running ReplayGain: {str(e)}")

    return {
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "cover_art_copied": cover_art_copied,
    }


def discover_and_sort_audio_files(directory):
    """Discover audio files in directory and return them sorted alphabetically.

    Args:
        directory: Path to directory to search

    Returns:
        List of Path objects for audio files, sorted alphabetically
    """
    from music_librarian.file_discovery import find_audio_files

    directory_path = Path(directory)
    audio_files = find_audio_files(directory_path)

    # Sort alphabetically by filename
    return sorted(audio_files, key=lambda p: str(p))


def extract_metadata_from_file(filepath):
    """Extract metadata from a single audio file.

    Args:
        filepath: Path to audio file

    Returns:
        Dict containing metadata fields
    """
    from music_librarian.metadata_handler import read_metadata_from_file

    try:
        metadata = read_metadata_from_file(filepath)
        # Ensure all expected fields are present
        result = {
            "title": metadata.get("title", ""),
            "artist": metadata.get("artist", ""),
            "album": metadata.get("album", ""),
            "date": metadata.get("date", ""),
            "track number": metadata.get("track number", ""),
        }
        return result
    except Exception:
        # If metadata extraction fails, return empty metadata
        return {"title": "", "artist": "", "album": "", "date": "", "track number": ""}


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
        audio_extensions = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".opus"}
        has_direct_audio_files = False

        for file_path in directory_path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
                has_direct_audio_files = True
                break

        if has_direct_audio_files:
            album_directories.append(directory_path)

    return album_directories


def discover_and_sort_audio_files_in_directory_only(directory):
    """Discover audio files only in the specified directory (not recursively).

    Args:
        directory: Path to directory to search

    Returns:
        List of Path objects for audio files in the directory only (not subdirectories)
    """
    directory_path = Path(directory)
    audio_extensions = {".flac", ".wav", ".mp3", ".ogg", ".aac", ".m4a", ".opus"}
    audio_files = []

    for file_path in directory_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
            audio_files.append(file_path.name)

    # Sort alphabetically by filename
    return sorted([Path(f) for f in audio_files])


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
        audio_files = discover_and_sort_audio_files_in_directory_only(directory)
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
            album_metadata = {
                "title": first_file_meta.get("album", ""),
                "artist": first_file_meta.get("artist", ""),
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
        except Exception as e:
            # If cover detection fails, just set empty cover
            album_metadata["cover"] = ""

        # Extract metadata for each file
        for audio_file in audio_files:
            filepath = directory_path / audio_file
            try:
                meta = extract_metadata_from_file(str(filepath))
                file_metadata[str(audio_file)] = {
                    "title": meta.get("title", ""),
                    "track number": meta.get("track number", ""),
                }
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
