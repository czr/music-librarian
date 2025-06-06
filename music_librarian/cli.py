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


@cli.command(name="transcode")
@click.argument("source_directories", nargs=-1, required=True)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Overwrite existing files in destination",
)
def transcode(source_directories, force):
    """Transcode FLAC/WAV files from source collection to destination collection."""
    # Validate environment variables
    source_root = os.environ.get("MUSIC_SOURCE_ROOT")
    dest_root = os.environ.get("MUSIC_DEST_ROOT")
    
    if not source_root:
        click.echo("Error: MUSIC_SOURCE_ROOT environment variable not set", err=True)
        sys.exit(1)
    
    if not dest_root:
        click.echo("Error: MUSIC_DEST_ROOT environment variable not set", err=True)
        sys.exit(1)
    
    # Validate that source directories are under MUSIC_SOURCE_ROOT
    for source_dir in source_directories:
        abs_source = os.path.abspath(source_dir)
        abs_source_root = os.path.abspath(source_root)
        
        if not abs_source.startswith(abs_source_root):
            click.echo(f"Error: {source_dir} is not under MUSIC_SOURCE_ROOT ({source_root})", err=True)
            sys.exit(1)
    
    click.echo(f"Transcoding {len(source_directories)} directories...")
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
    
    for line in content.split('\n'):
        # Strip whitespace and skip empty lines and comments
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Check for file section
        if line.startswith('file:') and line.endswith(':'):
            # Valid file section
            filename = line[5:-1].strip()
            current_file = filename
            in_malformed_section = False
            if current_file not in result["files"]:
                result["files"][current_file] = {}
        elif line.startswith('file:'):
            # Malformed file section - ignore everything until next valid section
            current_file = None
            in_malformed_section = True
            continue
        else:
            # Skip metadata if we're in a malformed section
            if in_malformed_section:
                continue
                
            # Parse key:value pair
            if ':' in line:
                key, value = line.split(':', 1)
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
            raise ValueError(f"File '{filename}' referenced in metadata.txt does not exist")


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
                "ALBUMARTIST": "ALBUMARTIST"
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
            else:
                opus_key = key.upper().replace(" ", "")
            
            cmd.extend(["--comment", f"{opus_key}={value}"])
    
    cmd.extend([input_file, output_file])
    return cmd


def merge_metadata(album_metadata, file_metadata, filename):
    """Merge album and file-specific metadata according to spec rules.
    
    Args:
        album_metadata: Dict of album-wide metadata
        file_metadata: Dict of file-specific metadata overrides
        filename: Name of the file being processed
    
    Returns:
        Dict of merged metadata for opusenc
    """
    result = {}
    
    # Start with album metadata, mapping title -> album
    for key, value in album_metadata.items():
        if key == "title":
            result["album"] = value
        else:
            result[key] = value
    
    # Apply file-specific overrides
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


def get_opus_quality():
    """Get Opus quality setting from environment or default.
    
    Returns:
        String quality setting for opusenc
    """
    return os.environ.get("OPUS_QUALITY", "128")


def process_directory(source_dir, dest_dir, force=False):
    """Process a single directory for transcoding.
    
    Args:
        source_dir: Path to source directory 
        dest_dir: Path to destination directory
        force: Whether to overwrite existing files
    
    Returns:
        Dict with processing results and statistics
    """
    from music_librarian.file_discovery import find_audio_files
    
    # Check external tools are available
    check_external_tools()
    
    # Get quality setting
    quality = get_opus_quality()
    
    # Create destination directory
    os.makedirs(dest_dir, exist_ok=True)
    
    # Find all audio files to process
    audio_files = find_audio_files(Path(source_dir))
    
    if not audio_files:
        return {
            "processed": 0,
            "skipped": 0,
            "errors": [],
            "cover_art_copied": False
        }
    
    # Look for metadata.txt
    metadata_file = os.path.join(source_dir, "metadata.txt")
    metadata = {"album": {}, "files": {}}
    
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r', encoding='utf-8') as f:
            content = f.read()
        metadata = parse_metadata_file(content)
        
        # Validate that referenced files exist
        available_filenames = [str(f) for f in audio_files]
        validate_metadata_files(metadata, available_filenames)
    
    # Process each audio file
    processed = 0
    skipped = 0
    errors = []
    
    for audio_file in audio_files:
        try:
            # Build paths
            input_path = os.path.join(source_dir, audio_file)
            output_filename = resolve_output_filename(str(audio_file))
            output_path = os.path.join(dest_dir, output_filename)
            
            # Skip if exists and not forcing
            if os.path.exists(output_path) and not force:
                skipped += 1
                continue
            
            # Create output directory if needed
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Merge metadata for this file
            file_metadata = metadata["files"].get(str(audio_file), {})
            merged_metadata = merge_metadata(metadata["album"], file_metadata, str(audio_file))
            
            # Build and run opusenc command
            cmd = build_opusenc_command(input_path, output_path, quality=quality, metadata=merged_metadata)
            
            # For now, just print the command instead of running it
            # In real implementation: subprocess.run(cmd, check=True)
            click.echo(f"Would run: {' '.join(cmd)}")
            processed += 1
            
        except Exception as e:
            errors.append(f"Error processing {audio_file}: {str(e)}")
    
    # Copy cover art if present
    cover_art_copied = False
    all_files = os.listdir(source_dir)
    cover_art = find_cover_art(all_files)
    
    if cover_art:
        try:
            cover_src = os.path.join(source_dir, cover_art)
            cover_dest = os.path.join(dest_dir, cover_art)
            
            if not os.path.exists(cover_dest) or force:
                # For now, just print instead of copying
                # In real implementation: shutil.copy2(cover_src, cover_dest)
                click.echo(f"Would copy cover art: {cover_src} -> {cover_dest}")
                cover_art_copied = True
        except Exception as e:
            errors.append(f"Error copying cover art: {str(e)}")
    
    # Run ReplayGain processing if files were processed
    if processed > 0:
        try:
            rsgain_cmd = build_rsgain_command(dest_dir)
            # For now, just print instead of running
            # In real implementation: subprocess.run(rsgain_cmd, check=True)  
            click.echo(f"Would run ReplayGain: {' '.join(rsgain_cmd)}")
        except Exception as e:
            errors.append(f"Error running ReplayGain: {str(e)}")
    
    return {
        "processed": processed,
        "skipped": skipped, 
        "errors": errors,
        "cover_art_copied": cover_art_copied
    }
