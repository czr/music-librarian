import os
import sys
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
    
    # TODO: Implement actual transcoding logic


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
