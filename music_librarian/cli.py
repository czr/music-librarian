import os
import sys
import tempfile
from pathlib import Path

import click

from music_librarian.exporter import (
    MissingTool,
    check_external_tools,
    process_directory,
    resolve_destination_path,
)
from music_librarian.extractor import extract_metadata_from_directory
from music_librarian.importer import ImportFailed, plan_imports, run_import


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

    _require_external_tools()

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
                click.echo("  Cover art copied")

            if result["errors"]:
                for error in result["errors"]:
                    click.echo(f"  Error: {error}", err=True)

        except Exception as e:
            error_msg = f"Failed to process directory {source_dir}: {str(e)}"
            total_errors.append(error_msg)
            click.echo(f"  Error: {error_msg}", err=True)

    # Summary
    click.echo("\nSummary:")
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
    click.echo("\nSummary:")
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
        _require_external_tools()

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


def _require_external_tools():
    try:
        check_external_tools()
    except MissingTool as e:
        click.echo(f"Error: {e}", err=True)
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
