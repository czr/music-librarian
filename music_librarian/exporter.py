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


def get_opus_quality():
    """Get Opus quality setting from environment or default.

    Returns:
        String quality setting for opusenc
    """
    return os.environ.get("OPUS_QUALITY", "128")


def process_directory(source_dir, dest_dir, force=False, debug=False):
    """Process a single directory for mixed audio formats (transcoding and copying).

    Each subdirectory containing audio is exported with its own metadata.txt
    and cover art; ReplayGain is then applied across the whole destination.

    Args:
        source_dir: Path to source directory
        dest_dir: Path to destination directory
        force: Whether to overwrite existing files
        debug: Whether to output debug information

    Returns:
        Dict with processing results and statistics
    """
    check_external_tools()
    quality = get_opus_quality()
    os.makedirs(dest_dir, exist_ok=True)

    files_by_directory = _audio_files_by_directory(Path(source_dir))
    if not files_by_directory:
        return {"processed": 0, "skipped": 0, "errors": [], "cover_art_copied": False}

    if debug:
        print(
            f"\n=== DEBUG: Found audio files in directories: {list(files_by_directory.keys())} ==="
        )

    total_processed = 0
    total_skipped = 0
    total_errors = []
    cover_art_copied = False

    for audio_dir, audio_files in files_by_directory.items():
        result = _export_audio_directory(
            source_dir, dest_dir, audio_dir, audio_files, quality, force, debug
        )
        total_processed += result["processed"]
        total_skipped += result["skipped"]
        total_errors.extend(result["errors"])
        cover_art_copied = cover_art_copied or result["cover_art_copied"]

    if total_processed > 0:
        total_errors.extend(_apply_replaygain(dest_dir))

    return {
        "processed": total_processed,
        "skipped": total_skipped,
        "errors": total_errors,
        "cover_art_copied": cover_art_copied,
    }


def _audio_files_by_directory(source_path):
    """Group audio files (relative paths) by their containing directory."""
    audio_files_by_type = find_audio_files_with_types(source_path)
    files_by_directory = {}
    for audio_file in audio_files_by_type["lossless"] + audio_files_by_type["lossy"]:
        audio_dir = os.path.dirname(str(audio_file))
        files_by_directory.setdefault(audio_dir, []).append(audio_file)
    return files_by_directory


def _export_audio_directory(
    source_dir, dest_dir, audio_dir, audio_files, quality, force, debug
):
    """Export the audio files directly within one directory, plus its cover art."""
    source_subdir = os.path.join(source_dir, audio_dir) if audio_dir else source_dir
    dest_subdir = os.path.join(dest_dir, audio_dir) if audio_dir else dest_dir
    result = {"processed": 0, "skipped": 0, "errors": [], "cover_art_copied": False}

    try:
        metadata = _load_metadata(source_subdir, audio_files, debug)
    except Exception as e:
        result["errors"].append(f"Error reading metadata.txt in {audio_dir}: {str(e)}")
        return result

    if audio_dir and not os.path.exists(dest_subdir):
        os.makedirs(dest_subdir, exist_ok=True)

    for audio_file in audio_files:
        try:
            if _export_audio_file(
                source_dir, dest_dir, audio_file, metadata, quality, force, debug
            ):
                result["processed"] += 1
            else:
                result["skipped"] += 1
        except Exception as e:
            result["errors"].append(f"Error processing {audio_file}: {str(e)}")

    result["cover_art_copied"] = _copy_cover_art(
        source_subdir, dest_subdir, audio_dir, metadata, force, debug, result["errors"]
    )
    return result


def _load_metadata(source_subdir, audio_files, debug):
    """Read and validate metadata.txt in a directory, if there is one."""
    metadata_file = os.path.join(source_subdir, "metadata.txt")
    if not os.path.exists(metadata_file):
        if debug:
            print(f"\n=== DEBUG: No metadata.txt found in {source_subdir} ===")
        return {"album": {}, "files": {}}

    if debug:
        print(f"\n=== DEBUG: Found metadata.txt in {source_subdir} ===")
    with open(metadata_file, "r", encoding="utf-8") as f:
        metadata = parse_metadata_file(f.read())
    validate_metadata_files(metadata, [os.path.basename(str(af)) for af in audio_files])
    return metadata


def _export_audio_file(
    source_dir, dest_dir, audio_file, metadata, quality, force, debug
):
    """Transcode or copy one audio file. Returns False if skipped as existing."""
    file_type = "lossless" if is_lossless_format(audio_file) else "lossy"

    # Build paths preserving relative directory structure
    input_path = os.path.join(source_dir, audio_file)
    output_path = os.path.join(
        dest_dir, get_output_filename(str(audio_file), file_type)
    )

    output_dir = os.path.dirname(output_path)
    if output_dir != dest_dir:
        os.makedirs(output_dir, exist_ok=True)

    if os.path.exists(output_path) and not force:
        return False

    # Merge metadata for this file (using relative filename within directory)
    relative_filename = os.path.basename(str(audio_file))
    file_metadata = get_normalized_file_metadata(metadata["files"], relative_filename)
    merged_metadata = merge_metadata(
        metadata["album"], file_metadata, relative_filename, input_path
    )

    if debug:
        print(f"\n=== DEBUG: Processing {audio_file} ===")
        print(f"File type: {file_type}")
        print(f"Album metadata: {metadata['album']}")
        print(f"File metadata: {file_metadata}")
        print(f"Merged metadata: {merged_metadata}")

    if file_type == "lossless":
        cmd = build_opusenc_command(
            input_path, output_path, quality=quality, metadata=merged_metadata
        )
        if debug:
            print(f"Opusenc command: {' '.join(cmd)}")
        subprocess.run(cmd, check=True, capture_output=True)
    else:
        if debug:
            print(f"Copying lossy file: {input_path} -> {output_path}")
            print(f"Applying metadata: {merged_metadata}")
        copy_with_metadata(input_path, output_path, merged_metadata)

    return True


def _copy_cover_art(
    source_subdir, dest_subdir, audio_dir, metadata, force, debug, errors
):
    """Copy a directory's cover art, appending any problems to `errors`.

    A cover named in metadata.txt is copied as cover.<ext>; otherwise the first
    file that looks like cover art is copied under its own name. Returns
    whether anything was copied.
    """
    specified_cover = metadata["album"].get("cover", "").strip()

    if debug:
        print(f"\n=== DEBUG: Cover art processing for {audio_dir} ===")
        print(f"Specified cover in metadata.txt: '{specified_cover}'")

    if specified_cover:
        try:
            cover_src = os.path.join(source_subdir, specified_cover)
            if not os.path.exists(cover_src):
                errors.append(
                    f"Cover file specified in metadata.txt not found: {specified_cover}"
                )
                return False
            _, ext = os.path.splitext(specified_cover)
            cover_dest = os.path.join(dest_subdir, f"cover{ext}")
            if not os.path.exists(cover_dest) or force:
                shutil.copy2(cover_src, cover_dest)
                return True
        except Exception as e:
            errors.append(
                f"Error copying specified cover art {specified_cover}: {str(e)}"
            )
        return False

    if not os.path.exists(source_subdir):
        return False
    cover_art = find_cover_art(os.listdir(source_subdir))
    if not cover_art:
        return False

    try:
        cover_src = os.path.join(source_subdir, cover_art)
        cover_dest = os.path.join(dest_subdir, cover_art)
        os.makedirs(dest_subdir, exist_ok=True)
        if not os.path.exists(cover_dest) or force:
            shutil.copy2(cover_src, cover_dest)
            return True
    except Exception as e:
        errors.append(f"Error copying cover art from {audio_dir}: {str(e)}")
    return False


def _apply_replaygain(dest_dir):
    """Run rsgain over the destination. Returns a list of errors."""
    try:
        with as_file(_rsgain_preset_ref()) as preset_path:
            rsgain_cmd = build_rsgain_command(dest_dir, preset_path)
            subprocess.run(rsgain_cmd, check=True, capture_output=True)
    except Exception as e:
        return [f"Error running ReplayGain: {str(e)}"]
    return []
