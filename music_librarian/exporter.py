"""Export albums from the source collection to the destination collection."""

import os
import shutil
import subprocess
from importlib.resources import as_file, files
from pathlib import Path


from music_librarian.audio_processor import (
    build_opusenc_command,
    copy_with_metadata,
    get_output_filename,
)
from music_librarian.file_discovery import (
    find_audio_files_with_types,
    find_cover_art,
    is_lossless_format,
)
from music_librarian.metadata_file import (
    get_normalized_file_metadata,
    merge_metadata,
    parse_metadata_file,
    validate_metadata_files,
)


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
    return get_output_filename(input_filename, file_type)


class MissingTool(Exception):
    """A required external tool isn't installed."""


def check_external_tools():
    """Check that required external tools are available.

    Raises:
        MissingTool: If any required tool is missing
    """
    tools = ["opusenc", "rsgain"]

    for tool in tools:
        if not shutil.which(tool):
            raise MissingTool(f"{tool} not found in PATH")


def _rsgain_preset_ref():
    """Return a Traversable reference to the bundled rsgain preset file."""
    return files("music_librarian").joinpath("data/rsgain_preset.ini")


def build_rsgain_command(directory, preset_path):
    """Build rsgain command for ReplayGain processing.

    Args:
        directory: Path to directory containing .opus files
        preset_path: Path to rsgain preset file

    Returns:
        List of command arguments for subprocess
    """
    return ["rsgain", "easy", "-p", str(preset_path), directory]


def build_rsgain_command_for_mixed_formats(directory, preset_path):
    """Build rsgain command for ReplayGain processing of mixed audio formats.

    Args:
        directory: Path to directory containing mixed audio files
        preset_path: Path to rsgain preset file

    Returns:
        List of command arguments for subprocess
    """
    return ["rsgain", "easy", "-p", str(preset_path), directory]


def get_opus_quality():
    """Get Opus quality setting from environment or default.

    Returns:
        String quality setting for opusenc
    """
    return os.environ.get("OPUS_QUALITY", "128")


def process_directory(source_dir, dest_dir, force=False, debug=False):
    """Process a single directory for mixed audio formats (transcoding and copying).

    Args:
        source_dir: Path to source directory
        dest_dir: Path to destination directory
        force: Whether to overwrite existing files
        debug: Whether to output debug information

    Returns:
        Dict with processing results and statistics
    """
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

    # Group audio files by their containing directory
    files_by_directory = {}
    for audio_file in all_audio_files:
        audio_dir = os.path.dirname(str(audio_file))
        if audio_dir not in files_by_directory:
            files_by_directory[audio_dir] = []
        files_by_directory[audio_dir].append(audio_file)

    if debug:
        print(
            f"\n=== DEBUG: Found audio files in directories: {list(files_by_directory.keys())} ==="
        )

    # Process each directory separately
    total_processed = 0
    total_skipped = 0
    total_errors = []
    cover_art_copied = False

    # Process each directory that contains audio files
    for audio_dir, audio_files in files_by_directory.items():
        # Build paths for this directory
        source_subdir = os.path.join(source_dir, audio_dir) if audio_dir else source_dir
        dest_subdir = os.path.join(dest_dir, audio_dir) if audio_dir else dest_dir

        # Look for metadata.txt in this specific directory
        metadata_file = os.path.join(source_subdir, "metadata.txt")
        metadata = {"album": {}, "files": {}}

        if os.path.exists(metadata_file):
            if debug:
                print(f"\n=== DEBUG: Found metadata.txt in {source_subdir} ===")
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata_content = f.read()
                metadata = parse_metadata_file(metadata_content)
                validate_metadata_files(
                    metadata, [os.path.basename(str(af)) for af in audio_files]
                )
            except Exception as e:
                total_errors.append(
                    f"Error reading metadata.txt in {audio_dir}: {str(e)}"
                )
                continue
        else:
            if debug:
                print(f"\n=== DEBUG: No metadata.txt found in {source_subdir} ===")

        # Create destination subdirectory if needed
        if audio_dir and not os.path.exists(dest_subdir):
            os.makedirs(dest_subdir, exist_ok=True)

        # Process each audio file in this directory
        processed = 0
        skipped = 0
        errors = []

        for audio_file in audio_files:
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

                # Merge metadata for this file (using relative filename within directory)
                relative_filename = os.path.basename(str(audio_file))
                file_metadata = get_normalized_file_metadata(
                    metadata["files"], relative_filename
                )
                merged_metadata = merge_metadata(
                    metadata["album"], file_metadata, relative_filename, input_path
                )

                if debug:
                    print(f"\n=== DEBUG: Processing {audio_file} ===")
                    print(f"File type: {file_type}")
                    print(f"Album metadata: {metadata['album']}")
                    print(f"File metadata: {file_metadata}")
                    print(f"Merged metadata: {merged_metadata}")

                # Process the file (transcode or copy based on type)
                if file_type == "lossless":
                    # Transcode lossless files to Opus
                    cmd = build_opusenc_command(
                        input_path,
                        output_path,
                        quality=quality,
                        metadata=merged_metadata,
                    )

                    if debug:
                        print(f"Opusenc command: {' '.join(cmd)}")

                    subprocess.run(cmd, check=True, capture_output=True)
                else:
                    # Copy lossy files and apply metadata
                    if debug:
                        print(f"Copying lossy file: {input_path} -> {output_path}")
                        print(f"Applying metadata: {merged_metadata}")

                    copy_with_metadata(input_path, output_path, merged_metadata)

                processed += 1

            except Exception as e:
                errors.append(f"Error processing {audio_file}: {str(e)}")

        # Handle cover art for this directory
        specified_cover = metadata["album"].get("cover", "").strip()

        if debug:
            print(f"\n=== DEBUG: Cover art processing for {audio_dir} ===")
            print(f"Specified cover in metadata.txt: '{specified_cover}'")

        if specified_cover:
            # Use cover specified in metadata.txt
            try:
                cover_src = os.path.join(source_subdir, specified_cover)
                if os.path.exists(cover_src):
                    # Extract extension and create cover.{ext} filename
                    _, ext = os.path.splitext(specified_cover)
                    cover_dest = os.path.join(dest_subdir, f"cover{ext}")

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

        # Update totals
        total_processed += processed
        total_skipped += skipped
        total_errors.extend(errors)

    # Run ReplayGain processing if files were processed
    if total_processed > 0:
        try:
            with as_file(_rsgain_preset_ref()) as preset_path:
                rsgain_cmd = build_rsgain_command_for_mixed_formats(
                    dest_dir, preset_path
                )
                subprocess.run(rsgain_cmd, check=True, capture_output=True)
        except Exception as e:
            total_errors.append(f"Error running ReplayGain: {str(e)}")

    return {
        "processed": total_processed,
        "skipped": total_skipped,
        "errors": total_errors,
        "cover_art_copied": cover_art_copied,
    }
