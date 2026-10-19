import os
import sys
import subprocess
import shutil
import tempfile
from importlib.resources import as_file, files
from pathlib import Path
import click

from music_librarian.extractor import extract_metadata_from_directory
from music_librarian.file_discovery import find_cover_art
from music_librarian.importer import ImportFailed, plan_imports, run_import
from music_librarian.metadata_file import (
    get_normalized_file_metadata,
    merge_metadata,
    parse_metadata_file,
    validate_metadata_files,
)


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
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug output showing commands and metadata",
)
def export(source_directories, force, debug):
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
            result = process_directory(source_dir, dest_dir, force=force, debug=debug)

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


@cli.command(name="import")
@click.argument("sources", nargs=-1, required=True, type=click.Path(path_type=Path))
@click.option(
    "--export",
    "export_after",
    is_flag=True,
    help="Export each album after importing it",
)
@click.option(
    "--no-metadata",
    is_flag=True,
    help="Don't generate metadata.txt in imported albums",
)
def import_command(sources, export_after, no_metadata):
    """Import downloaded albums (zip files or folders) into MUSIC_SOURCE_ROOT."""
    source_root = os.environ.get("MUSIC_SOURCE_ROOT", "").strip()
    if not source_root:
        click.echo("Error: MUSIC_SOURCE_ROOT environment variable not set", err=True)
        sys.exit(1)
    library_root = Path(source_root)
    if not library_root.is_dir():
        click.echo(f"Error: MUSIC_SOURCE_ROOT ({source_root}) does not exist", err=True)
        sys.exit(1)

    dest_root = os.environ.get("MUSIC_DEST_ROOT", "").strip()
    if export_after:
        if not dest_root:
            click.echo("Error: MUSIC_DEST_ROOT environment variable not set", err=True)
            sys.exit(1)
        check_external_tools()

    imported = []
    with tempfile.TemporaryDirectory() as workdir:
        try:
            plans = plan_imports(
                [source.expanduser() for source in sources],
                library_root,
                Path(workdir),
            )
            for plan in plans:
                click.echo(_describe_import(plan))
                imported.append(
                    run_import(plan, library_root, create_metadata=not no_metadata)
                )
        except ImportFailed as e:
            click.echo(f"Error: {e}", err=True)
            _report_partial_import(imported, library_root)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Error: import failed: {e}", err=True)
            _report_partial_import(imported, library_root)
            sys.exit(1)

    if not export_after:
        return

    errors = []
    for album_dir in imported:
        relative = album_dir.relative_to(library_root)
        click.echo(f"\nExporting: {relative}")
        try:
            result = process_directory(
                str(album_dir),
                resolve_destination_path(str(album_dir), str(library_root), dest_root),
            )
            click.echo(f"  Processed: {result['processed']} files")
            errors.extend(f"{relative}: {error}" for error in result["errors"])
        except Exception as e:
            errors.append(f"{relative}: {e}")

    if errors:
        for error in errors:
            click.echo(f"Error exporting {error}", err=True)
        click.echo(
            "The imports are complete; fix the problem and rerun export.", err=True
        )
        sys.exit(1)


def _plural(count, noun):
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _describe_import(plan):
    details = _plural(plan.track_count, "track")
    if plan.other_count:
        details += f", {_plural(plan.other_count, 'other file')}"
    line = f"{plan.source.name} → {plan.relative_destination}/ ({details})"
    if plan.new_artist:
        line += " [new artist]"
    return line


def _report_partial_import(imported, library_root):
    if imported:
        click.echo("Already imported before the error:", err=True)
        for album_dir in imported:
            click.echo(f"  {album_dir.relative_to(library_root)}", err=True)


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
                    from music_librarian.audio_processor import copy_with_metadata

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
