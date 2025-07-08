import os
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
import pytest
from click.testing import CliRunner
from music_librarian.cli import cli
from music_librarian.file_discovery import find_audio_files


def test_version():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert result.output.startswith("cli, version ")


class TestExportCLI:
    """Tests for the export command CLI interface."""

    def test_export_requires_source_directory(self):
        """Test that export command requires at least one source directory."""
        runner = CliRunner()
        result = runner.invoke(cli, ["export"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_export_missing_source_root_env(self):
        """Test that export fails when MUSIC_SOURCE_ROOT is not set."""
        runner = CliRunner()
        env = {"MUSIC_DEST_ROOT": "/dest", "MUSIC_SOURCE_ROOT": ""}
        result = runner.invoke(cli, ["export", "/some/path"], env=env)
        assert result.exit_code == 1
        assert "MUSIC_SOURCE_ROOT environment variable not set" in result.output

    def test_export_missing_dest_root_env(self):
        """Test that export fails when MUSIC_DEST_ROOT is not set."""
        runner = CliRunner()
        env = {"MUSIC_SOURCE_ROOT": "/source", "MUSIC_DEST_ROOT": ""}
        result = runner.invoke(cli, ["export", "/some/path"], env=env)
        assert result.exit_code == 1
        assert "MUSIC_DEST_ROOT environment variable not set" in result.output

    def test_export_source_not_under_root(self):
        """Test that export fails when source directory is not under MUSIC_SOURCE_ROOT."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_root = os.path.abspath("music_source")
            dest_root = os.path.abspath("music_dest")
            bad_source = os.path.abspath("other_location")

            os.makedirs(source_root)
            os.makedirs(dest_root)
            os.makedirs(bad_source)

            env = {"MUSIC_SOURCE_ROOT": source_root, "MUSIC_DEST_ROOT": dest_root}

            result = runner.invoke(cli, ["export", bad_source], env=env)
            assert result.exit_code == 1
            assert f"is not under MUSIC_SOURCE_ROOT" in result.output

    def test_export_valid_single_directory(self):
        """Test that export accepts valid single source directory."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_root = os.path.abspath("music_source")
            dest_root = os.path.abspath("music_dest")
            album_dir = os.path.join(source_root, "artist", "album")

            os.makedirs(album_dir)
            os.makedirs(dest_root)

            env = {"MUSIC_SOURCE_ROOT": source_root, "MUSIC_DEST_ROOT": dest_root}

            result = runner.invoke(cli, ["export", album_dir], env=env)
            # Should not exit with error for validation
            assert "is not under MUSIC_SOURCE_ROOT" not in result.output
            assert "environment variable not set" not in result.output

    def test_export_valid_multiple_directories(self):
        """Test that export accepts multiple valid source directories."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_root = os.path.abspath("music_source")
            dest_root = os.path.abspath("music_dest")
            album1_dir = os.path.join(source_root, "artist1", "album1")
            album2_dir = os.path.join(source_root, "artist2", "album2")

            os.makedirs(album1_dir)
            os.makedirs(album2_dir)
            os.makedirs(dest_root)

            env = {"MUSIC_SOURCE_ROOT": source_root, "MUSIC_DEST_ROOT": dest_root}

            result = runner.invoke(cli, ["export", album1_dir, album2_dir], env=env)
            assert "is not under MUSIC_SOURCE_ROOT" not in result.output
            assert "environment variable not set" not in result.output

    def test_export_force_flag(self):
        """Test that --force flag is properly parsed."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_root = os.path.abspath("music_source")
            dest_root = os.path.abspath("music_dest")
            album_dir = os.path.join(source_root, "artist", "album")

            os.makedirs(album_dir)
            os.makedirs(dest_root)

            env = {"MUSIC_SOURCE_ROOT": source_root, "MUSIC_DEST_ROOT": dest_root}

            result = runner.invoke(cli, ["export", "--force", album_dir], env=env)
            assert "Force overwrite: True" in result.output

    def test_export_no_force_flag(self):
        """Test default behavior without --force flag."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_root = os.path.abspath("music_source")
            dest_root = os.path.abspath("music_dest")
            album_dir = os.path.join(source_root, "artist", "album")

            os.makedirs(album_dir)
            os.makedirs(dest_root)

            env = {"MUSIC_SOURCE_ROOT": source_root, "MUSIC_DEST_ROOT": dest_root}

            result = runner.invoke(cli, ["export", album_dir], env=env)
            assert "Force overwrite: False" in result.output


class TestPathResolution:
    """Tests for path resolution and destination mapping."""

    def test_resolve_destination_path_single_level(self):
        """Test resolving destination path for single level directory."""
        from music_librarian.cli import resolve_destination_path

        source_root = "/media/external/flac"
        dest_root = "/home/user/music/opus"
        source_dir = "/media/external/flac/artist"

        expected = "/home/user/music/opus/artist"
        result = resolve_destination_path(source_dir, source_root, dest_root)
        assert result == expected

    def test_resolve_destination_path_nested(self):
        """Test resolving destination path for nested directories."""
        from music_librarian.cli import resolve_destination_path

        source_root = "/media/external/flac"
        dest_root = "/home/user/music/opus"
        source_dir = "/media/external/flac/Pink Floyd/Dark Side of the Moon"

        expected = "/home/user/music/opus/Pink Floyd/Dark Side of the Moon"
        result = resolve_destination_path(source_dir, source_root, dest_root)
        assert result == expected

    def test_resolve_destination_path_exact_root(self):
        """Test resolving destination path when source is exactly the root."""
        from music_librarian.cli import resolve_destination_path

        source_root = "/media/external/flac"
        dest_root = "/home/user/music/opus"
        source_dir = "/media/external/flac"

        expected = "/home/user/music/opus"
        result = resolve_destination_path(source_dir, source_root, dest_root)
        assert result == expected

    def test_resolve_destination_path_with_trailing_slashes(self):
        """Test path resolution handles trailing slashes correctly."""
        from music_librarian.cli import resolve_destination_path

        source_root = "/media/external/flac/"
        dest_root = "/home/user/music/opus/"
        source_dir = "/media/external/flac/artist/album/"

        expected = "/home/user/music/opus/artist/album"
        result = resolve_destination_path(source_dir, source_root, dest_root)
        assert result == expected

    def test_resolve_output_filename(self):
        """Test converting input filenames to output .opus filenames."""
        from music_librarian.cli import resolve_output_filename

        test_cases = [
            ("track.flac", "track.opus"),
            ("song.wav", "song.opus"),
            ("01 - Title.flac", "01 - Title.opus"),
            ("nested/path/file.wav", "nested/path/file.opus"),
        ]

        for input_file, expected in test_cases:
            result = resolve_output_filename(input_file)
            assert result == expected


class TestMetadataParsing:
    """Tests for metadata.txt parsing functionality."""

    def test_parse_album_metadata_only(self):
        """Test parsing metadata.txt with only album-wide metadata."""
        from music_librarian.cli import parse_metadata_file

        metadata_content = """title: TERROR 404
artist: Perturbator
date: 2012
"""

        expected = {
            "album": {"title": "TERROR 404", "artist": "Perturbator", "date": "2012"},
            "files": {},
        }

        result = parse_metadata_file(metadata_content)
        assert result == expected

    def test_parse_file_specific_metadata(self):
        """Test parsing metadata.txt with file-specific overrides."""
        from music_librarian.cli import parse_metadata_file

        metadata_content = """title: TERROR 404
artist: Perturbator
date: 2012

file: track1.flac:
track number: 01
title: Opening Credits

file: track2.flac:
artist: Perturbator & Guest
track number: 02
title: Mirage
"""

        expected = {
            "album": {"title": "TERROR 404", "artist": "Perturbator", "date": "2012"},
            "files": {
                "track1.flac": {"track number": "01", "title": "Opening Credits"},
                "track2.flac": {
                    "artist": "Perturbator & Guest",
                    "track number": "02",
                    "title": "Mirage",
                },
            },
        }

        result = parse_metadata_file(metadata_content)
        assert result == expected

    def test_parse_empty_values(self):
        """Test parsing metadata.txt with empty values."""
        from music_librarian.cli import parse_metadata_file

        metadata_content = """title:
artist: Test Artist
date: 2023

file: track1.flac:
title:
track number: 01
"""

        expected = {
            "album": {"title": "", "artist": "Test Artist", "date": "2023"},
            "files": {"track1.flac": {"title": "", "track number": "01"}},
        }

        result = parse_metadata_file(metadata_content)
        assert result == expected

    def test_parse_with_whitespace(self):
        """Test parsing handles leading/trailing whitespace correctly."""
        from music_librarian.cli import parse_metadata_file

        metadata_content = """  title:   Album Title
artist:Perturbator
date:  2012

file:  track1.flac  :
  title:  Track Title
track number:  01
"""

        expected = {
            "album": {"title": "Album Title", "artist": "Perturbator", "date": "2012"},
            "files": {"track1.flac": {"title": "Track Title", "track number": "01"}},
        }

        result = parse_metadata_file(metadata_content)
        assert result == expected

    def test_parse_case_sensitive_fields(self):
        """Test that field names are case-sensitive."""
        from music_librarian.cli import parse_metadata_file

        metadata_content = """Title: Should Not Match
title: Correct Title
Artist: Should Not Match
artist: Correct Artist
"""

        expected = {
            "album": {
                "Title": "Should Not Match",
                "title": "Correct Title",
                "Artist": "Should Not Match",
                "artist": "Correct Artist",
            },
            "files": {},
        }

        result = parse_metadata_file(metadata_content)
        assert result == expected

    def test_parse_comments_and_empty_lines(self):
        """Test parsing ignores comments and empty lines."""
        from music_librarian.cli import parse_metadata_file

        metadata_content = """# This is a comment
title: Album Title
# Another comment
artist: Artist Name

# Comment before file section
file: track1.flac:
title: Track Title
# Comment in file section
track number: 01

"""

        expected = {
            "album": {"title": "Album Title", "artist": "Artist Name"},
            "files": {"track1.flac": {"title": "Track Title", "track number": "01"}},
        }

        result = parse_metadata_file(metadata_content)
        assert result == expected

    def test_parse_malformed_file_section(self):
        """Test parsing handles malformed file sections gracefully."""
        from music_librarian.cli import parse_metadata_file

        metadata_content = """title: Album Title

file: missing_colon_at_end
title: This should not be parsed

file: correct_file.flac:
title: This should be parsed
"""

        expected = {
            "album": {"title": "Album Title"},
            "files": {"correct_file.flac": {"title": "This should be parsed"}},
        }

        result = parse_metadata_file(metadata_content)
        assert result == expected

    def test_validate_files_exist(self):
        """Test validation that files referenced in metadata.txt exist."""
        from music_librarian.cli import validate_metadata_files

        metadata = {
            "album": {"title": "Test Album"},
            "files": {
                "existing.flac": {"title": "Track 1"},
                "missing.flac": {"title": "Track 2"},
            },
        }

        available_files = ["existing.flac", "other.wav"]

        # Should raise error for missing file
        with pytest.raises(ValueError, match="missing.flac"):
            validate_metadata_files(metadata, available_files)

    def test_validate_files_all_exist(self):
        """Test validation passes when all files exist."""
        from music_librarian.cli import validate_metadata_files

        metadata = {
            "album": {"title": "Test Album"},
            "files": {
                "track1.flac": {"title": "Track 1"},
                "track2.wav": {"title": "Track 2"},
            },
        }

        available_files = ["track1.flac", "track2.wav", "extra.flac"]

        # Should not raise any error
        validate_metadata_files(metadata, available_files)

    def test_validate_unicode_filenames_nfd_nfc_mismatch(self):
        """Test validation with Unicode filenames that have NFD/NFC normalization differences."""
        from music_librarian.cli import validate_metadata_files

        # Create a filename with accented characters
        # NFD (decomposed) form: 'u' + combining umlaut
        filename_nfd = "04-THYX-Fu\u0308rImmer.flac"
        # NFC (composed) form: 'ü' as single character
        filename_nfc = "04-THYX-FürImmer.flac"

        # Verify they are different byte sequences but same visual representation
        assert filename_nfd != filename_nfc
        assert unicodedata.normalize("NFD", filename_nfd) == unicodedata.normalize(
            "NFD", filename_nfc
        )

        metadata = {
            "album": {"title": "Test Album"},
            "files": {
                filename_nfd: {"title": "Unicode Track"},
            },
        }

        # Available files list has the NFC form (as might happen on different filesystems)
        available_files = [filename_nfc]

        # Should not raise any error due to normalization
        validate_metadata_files(metadata, available_files)

    def test_validate_unicode_filenames_still_missing(self):
        """Test validation with Unicode filenames that are genuinely missing."""
        from music_librarian.cli import validate_metadata_files

        metadata = {
            "album": {"title": "Test Album"},
            "files": {
                "04-THYX-FürImmer.flac": {"title": "Unicode Track"},
                "existing.flac": {"title": "Normal Track"},
            },
        }

        # Available files list doesn't have the Unicode file
        available_files = ["existing.flac", "other.wav"]

        # Should raise error for missing Unicode file
        with pytest.raises(ValueError, match="04-THYX-FürImmer.flac"):
            validate_metadata_files(metadata, available_files)

    def test_validate_unicode_filenames_all_exist(self):
        """Test validation passes when all Unicode files exist."""
        from music_librarian.cli import validate_metadata_files

        metadata = {
            "album": {"title": "Test Album"},
            "files": {
                "track_with_unicode_文件名.flac": {"title": "Chinese Track"},
                "04-THYX-FürImmer.flac": {"title": "German Track"},
                "normal_track.flac": {"title": "Normal Track"},
            },
        }

        available_files = [
            "track_with_unicode_文件名.flac",
            "04-THYX-FürImmer.flac",
            "normal_track.flac",
        ]

        # Should not raise any error
        validate_metadata_files(metadata, available_files)


class TestCoverArt:
    """Tests for cover art detection and copying functionality."""

    def test_find_cover_art_basic_patterns(self):
        """Test finding cover art files with basic naming patterns."""
        from music_librarian.cli import find_cover_art

        available_files = ["track1.flac", "track2.flac", "cover.jpg", "readme.txt"]

        result = find_cover_art(available_files)
        assert result == "cover.jpg"

    def test_find_cover_art_case_insensitive(self):
        """Test case-insensitive cover art detection."""
        from music_librarian.cli import find_cover_art

        test_cases = [
            (["COVER.JPG", "track.flac"], "COVER.JPG"),
            (["Cover.jpg", "track.flac"], "Cover.jpg"),
            (["FOLDER.PNG", "track.flac"], "FOLDER.PNG"),
            (["front.JPEG", "track.flac"], "front.JPEG"),
            (["Album.webp", "track.flac"], "Album.webp"),
        ]

        for files, expected in test_cases:
            result = find_cover_art(files)
            assert result == expected

    def test_find_cover_art_multiple_candidates(self):
        """Test that first matching cover art file is returned."""
        from music_librarian.cli import find_cover_art

        available_files = [
            "track1.flac",
            "cover.jpg",  # Should be found first
            "folder.png",
            "front.jpeg",
        ]

        result = find_cover_art(available_files)
        assert result == "cover.jpg"

    def test_find_cover_art_different_extensions(self):
        """Test finding cover art with different supported extensions."""
        from music_librarian.cli import find_cover_art

        test_cases = [
            (["cover.jpg"], "cover.jpg"),
            (["cover.jpeg"], "cover.jpeg"),
            (["cover.png"], "cover.png"),
            (["cover.gif"], "cover.gif"),
            (["cover.webp"], "cover.webp"),
        ]

        for files, expected in test_cases:
            result = find_cover_art(files)
            assert result == expected

    def test_find_cover_art_no_match(self):
        """Test behavior when no cover art files are found."""
        from music_librarian.cli import find_cover_art

        available_files = ["track1.flac", "track2.wav", "metadata.txt", "readme.txt"]

        result = find_cover_art(available_files)
        assert result is None

    def test_find_cover_art_priority_order(self):
        """Test that cover art files are found in priority order."""
        from music_librarian.cli import find_cover_art

        # Based on the spec: cover, folder, front, album
        available_files = [
            "album.jpg",  # Lower priority
            "front.jpg",  # Medium priority
            "folder.jpg",  # High priority
            "cover.jpg",  # Highest priority
            "track.flac",
        ]

        result = find_cover_art(available_files)
        assert result == "cover.jpg"

    def test_find_cover_art_without_audio_files(self):
        """Test finding cover art in directory without audio files."""
        from music_librarian.cli import find_cover_art

        available_files = ["cover.jpg", "readme.txt", "metadata.txt"]

        result = find_cover_art(available_files)
        assert result == "cover.jpg"


class TestOpusencIntegration:
    """Tests for opusenc transcoding integration."""

    def test_build_opusenc_command_basic(self):
        """Test building basic opusenc command without metadata overrides."""
        from music_librarian.cli import build_opusenc_command

        input_file = "/source/track.flac"
        output_file = "/dest/track.opus"

        result = build_opusenc_command(input_file, output_file)

        expected = [
            "opusenc",
            "--discard-comments",
            "/source/track.flac",
            "/dest/track.opus",
        ]

        assert result == expected

    def test_build_opusenc_command_with_quality(self):
        """Test building opusenc command with quality setting."""
        from music_librarian.cli import build_opusenc_command

        input_file = "/source/track.flac"
        output_file = "/dest/track.opus"
        quality = "192"

        result = build_opusenc_command(input_file, output_file, quality=quality)

        expected = [
            "opusenc",
            "--bitrate",
            "192",
            "--discard-comments",
            "/source/track.flac",
            "/dest/track.opus",
        ]

        assert result == expected

    def test_build_opusenc_command_with_metadata(self):
        """Test building opusenc command with metadata overrides."""
        from music_librarian.cli import build_opusenc_command

        input_file = "/source/track.flac"
        output_file = "/dest/track.opus"
        metadata = {
            "title": "Track Title",
            "artist": "Artist Name",
            "album": "Album Title",
            "date": "2023",
            "track number": "01",
        }

        result = build_opusenc_command(input_file, output_file, metadata=metadata)

        expected = [
            "opusenc",
            "--discard-comments",
            "--title",
            "Track Title",
            "--artist",
            "Artist Name",
            "--album",
            "Album Title",
            "--date",
            "2023",
            "--tracknumber",
            "01",
            "/source/track.flac",
            "/dest/track.opus",
        ]

        assert result == expected

    def test_build_opusenc_command_with_quality_and_metadata(self):
        """Test building opusenc command with both quality and metadata."""
        from music_librarian.cli import build_opusenc_command

        input_file = "/source/track.flac"
        output_file = "/dest/track.opus"
        quality = "128"
        metadata = {"title": "Test Track", "artist": "Test Artist"}

        result = build_opusenc_command(
            input_file, output_file, quality=quality, metadata=metadata
        )

        expected = [
            "opusenc",
            "--bitrate",
            "128",
            "--discard-comments",
            "--title",
            "Test Track",
            "--artist",
            "Test Artist",
            "/source/track.flac",
            "/dest/track.opus",
        ]

        assert result == expected

    def test_build_opusenc_command_empty_metadata_values(self):
        """Test building opusenc command with empty metadata values."""
        from music_librarian.cli import build_opusenc_command

        input_file = "/source/track.flac"
        output_file = "/dest/track.opus"
        metadata = {"title": "", "artist": "Artist Name"}

        result = build_opusenc_command(input_file, output_file, metadata=metadata)

        expected = [
            "opusenc",
            "--discard-comments",
            "--artist",
            "Artist Name",
            "/source/track.flac",
            "/dest/track.opus",
        ]

        assert result == expected

    def test_check_opusenc_available(self):
        """Test checking if opusenc is available in PATH."""
        from music_librarian.cli import check_external_tools

        # Should not raise an exception since opusenc is available
        check_external_tools()

    def test_merge_metadata_album_only(self):
        """Test merging album metadata without file-specific overrides."""
        from music_librarian.cli import merge_metadata

        album_metadata = {
            "title": "Album Title",
            "artist": "Album Artist",
            "date": "2023",
        }

        file_metadata = {}
        filename = "track.flac"

        result = merge_metadata(album_metadata, file_metadata, filename)

        expected = {"album": "Album Title", "artist": "Album Artist", "date": "2023"}

        assert result == expected

    def test_merge_metadata_with_file_overrides(self):
        """Test merging metadata with file-specific overrides."""
        from music_librarian.cli import merge_metadata

        album_metadata = {
            "title": "Album Title",
            "artist": "Album Artist",
            "date": "2023",
        }

        file_metadata = {"title": "Track Title", "track number": "01"}

        filename = "track.flac"

        result = merge_metadata(album_metadata, file_metadata, filename)

        expected = {
            "album": "Album Title",
            "artist": "Album Artist",  # Album artist preserved
            "date": "2023",
            "title": "Track Title",  # Overridden by file metadata
            "track number": "01",
        }

        assert result == expected

    def test_merge_metadata_artist_override_preserves_album_artist(self):
        """Test that overriding artist preserves album artist."""
        from music_librarian.cli import merge_metadata

        album_metadata = {"title": "Album Title", "artist": "Album Artist"}

        file_metadata = {"artist": "Track Artist"}

        filename = "track.flac"

        result = merge_metadata(album_metadata, file_metadata, filename)

        expected = {
            "album": "Album Title",
            "artist": "Track Artist",  # Overridden
            "albumartist": "Album Artist",  # Preserved from album
        }

        assert result == expected

    def test_merge_metadata_with_source_file_metadata(self):
        """Test merging source file metadata with metadata.txt overrides."""
        from music_librarian.cli import merge_metadata
        from unittest.mock import patch

        # Mock source file metadata
        source_metadata = {
            "title": "Original Title",
            "artist": "Original Artist",
            "album": "Original Album",
            "date": "2020",
            "genre": "Rock",
        }

        album_metadata = {
            "title": "Album Title",
            "artist": "Album Artist",
            "date": "2023",
        }

        file_metadata = {"title": "Track Title", "track number": "01"}

        filename = "track.flac"

        # Mock the metadata reading function
        with patch(
            "music_librarian.metadata_handler.read_metadata_from_file"
        ) as mock_read:
            mock_read.return_value = source_metadata

            result = merge_metadata(
                album_metadata, file_metadata, filename, "/fake/path/track.flac"
            )

        # Expected: source metadata is base, album metadata overrides some fields,
        # file metadata overrides specific fields
        expected = {
            "title": "Track Title",  # From file metadata (highest priority)
            "artist": "Album Artist",  # From album metadata
            "album": "Album Title",  # From album metadata (title -> album mapping)
            "date": "2023",  # From album metadata
            "genre": "Rock",  # From source metadata (preserved)
            "track number": "01",  # From file metadata
        }

        assert result == expected

    def test_merge_metadata_source_file_override_replacement(self):
        """Test that metadata.txt completely replaces source file tags."""
        from music_librarian.cli import merge_metadata
        from unittest.mock import patch

        # Source file has multiple artists (the original problem case)
        source_metadata = {
            "title": "Original Title",
            "artist": "Original Artist",
            "album": "Original Album",
        }

        album_metadata = {}

        file_metadata = {
            "artist": "New Artist"  # This should completely replace the source artist
        }

        filename = "track.flac"

        with patch(
            "music_librarian.metadata_handler.read_metadata_from_file"
        ) as mock_read:
            mock_read.return_value = source_metadata

            result = merge_metadata(
                album_metadata, file_metadata, filename, "/fake/path/track.flac"
            )

        # The source artist should be completely replaced, not added to
        expected = {
            "title": "Original Title",  # From source (unchanged)
            "artist": "New Artist",  # From file metadata (replaces source)
            "album": "Original Album",  # From source (unchanged)
        }

        assert result == expected

    def test_merge_metadata_no_source_file_fallback(self):
        """Test that merge_metadata works when source file can't be read."""
        from music_librarian.cli import merge_metadata
        from unittest.mock import patch

        album_metadata = {"title": "Album Title", "artist": "Album Artist"}
        file_metadata = {"title": "Track Title"}
        filename = "track.flac"

        # Mock metadata reading to raise an exception
        with patch(
            "music_librarian.metadata_handler.read_metadata_from_file"
        ) as mock_read:
            mock_read.side_effect = Exception("Cannot read file")

            result = merge_metadata(
                album_metadata, file_metadata, filename, "/fake/path/track.flac"
            )

        # Should work exactly like the old behavior when source file can't be read
        expected = {
            "album": "Album Title",
            "artist": "Album Artist",
            "title": "Track Title",
        }

        assert result == expected

    def test_merge_metadata_source_file_path_none(self):
        """Test that merge_metadata works when no source file path is provided."""
        from music_librarian.cli import merge_metadata

        album_metadata = {"title": "Album Title", "artist": "Album Artist"}
        file_metadata = {"title": "Track Title"}
        filename = "track.flac"

        result = merge_metadata(album_metadata, file_metadata, filename, None)

        # Should work exactly like the old behavior when no source file path provided
        expected = {
            "album": "Album Title",
            "artist": "Album Artist",
            "title": "Track Title",
        }

        assert result == expected

    def test_merge_metadata_unicode_filename_normalization(self):
        """Test that merge_metadata correctly handles Unicode filename normalization."""
        import unicodedata
        from music_librarian.cli import (
            merge_metadata,
            parse_metadata_file,
            validate_metadata_files,
            get_normalized_file_metadata,
        )

        # Create a filename with accented characters
        # NFD (decomposed) form: 'u' + combining umlaut
        filename_nfd = "04-THYX-Fu\u0308rImmer.flac"
        # NFC (composed) form: 'ü' as single character
        filename_nfc = "04-THYX-FürImmer.flac"

        # Verify they are different byte sequences but same visual representation
        assert filename_nfd != filename_nfc
        assert unicodedata.normalize("NFD", filename_nfd) == unicodedata.normalize(
            "NFD", filename_nfc
        )

        # Create metadata.txt content with NFD filename
        metadata_content = f"""title: Test Album
artist: Test Artist
date: 2023

file: {filename_nfd}:
title: Unicode Track Title
track number: 04
"""

        # Parse the metadata
        metadata = parse_metadata_file(metadata_content)

        # Simulate filesystem having NFC filename (common on macOS)
        available_files = [filename_nfc]

        # Validation should pass due to normalization
        validate_metadata_files(metadata, available_files)

        # Test the helper function directly
        file_metadata = get_normalized_file_metadata(metadata["files"], filename_nfc)

        # Should find the file-specific metadata despite normalization difference
        assert file_metadata["title"] == "Unicode Track Title"
        assert file_metadata["track number"] == "04"

        # Test merge_metadata with the normalized lookup
        result = merge_metadata(metadata["album"], file_metadata, filename_nfc)

        # Should now work correctly
        assert result["title"] == "Unicode Track Title"
        assert result["track number"] == "04"


class TestReplayGainIntegration:
    """Tests for ReplayGain processing with rsgain."""

    def test_build_rsgain_command(self):
        """Test building rsgain command for directory processing."""
        from music_librarian.cli import build_rsgain_command

        directory = "/dest/album"

        result = build_rsgain_command(directory)

        expected = ["rsgain", "easy", "/dest/album"]

        assert result == expected

    def test_check_rsgain_available(self):
        """Test checking if rsgain is available in PATH."""
        from music_librarian.cli import check_external_tools

        # Should not raise an exception since rsgain is available
        check_external_tools()


class TestExportWorkflow:
    """Integration tests for complete export workflow."""

    def create_test_flac_file(self, filepath):
        """Create a minimal test FLAC file using ffmpeg."""
        # Generate 1 second of silence as FLAC
        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            "1",
            "-c:a",
            "flac",
            "-y",  # Overwrite without asking
            str(filepath),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def create_test_cover_art(self, filepath):
        """Create a minimal test cover art file."""
        # Create a simple 1x1 pixel JPG using ffmpeg
        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "color=red:size=1x1:duration=1",
            "-frames:v",
            "1",
            "-y",  # Overwrite without asking
            str(filepath),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def test_process_directory_creates_nested_directories(self):
        """Test that processing creates nested Artist/Album directory structure."""
        from music_librarian.cli import process_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source directory with nested artist/album structure
            artist_source_dir = os.path.join(temp_dir, "source", "Pink Floyd")
            album_source_dir = os.path.join(artist_source_dir, "Dark Side of the Moon")
            os.makedirs(album_source_dir)

            # Create test FLAC file
            flac_file = os.path.join(album_source_dir, "01 - Speak to Me.flac")
            self.create_test_flac_file(flac_file)

            # Create test cover art
            cover_file = os.path.join(album_source_dir, "cover.jpg")
            self.create_test_cover_art(cover_file)

            # Define destination path that doesn't exist yet
            artist_dest_dir = os.path.join(temp_dir, "dest", "Pink Floyd")
            album_dest_dir = os.path.join(artist_dest_dir, "Dark Side of the Moon")

            # Verify destination directory doesn't exist before processing
            assert not os.path.exists(
                artist_dest_dir
            ), "Parent destination directory should not exist initially"
            assert not os.path.exists(
                album_dest_dir
            ), "Album destination directory should not exist initially"

            # Process the directory - this should create all necessary directories
            result = process_directory(artist_source_dir, artist_dest_dir, force=True)

            # Verify processing was successful
            assert result["processed"] == 1
            assert result["skipped"] == 0
            assert result["cover_art_copied"] == True
            assert len(result["errors"]) == 0

            # Verify that nested directories were created
            assert os.path.exists(
                album_dest_dir
            ), "Album destination directory should be created"
            assert os.path.isdir(
                album_dest_dir
            ), "Album destination should be a directory"

            # Verify output files exist in the correct nested location
            expected_opus = os.path.join(album_dest_dir, "01 - Speak to Me.opus")
            expected_cover = os.path.join(album_dest_dir, "cover.jpg")

            assert os.path.exists(
                expected_opus
            ), "Opus file should be created in nested directory"
            assert os.path.exists(
                expected_cover
            ), "Cover art should be copied to nested directory"

            # Verify opus file is not empty
            assert os.path.getsize(expected_opus) > 0, "Opus file should not be empty"

    def test_process_directory_with_flac_file(self):
        """Test processing a directory with actual FLAC files and cover art."""
        from music_librarian.cli import process_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source and destination directories
            source_dir = os.path.join(temp_dir, "source")
            dest_dir = os.path.join(temp_dir, "dest")
            os.makedirs(source_dir)

            # Create test FLAC file
            flac_file = os.path.join(source_dir, "test.flac")
            self.create_test_flac_file(flac_file)

            # Create test cover art
            cover_file = os.path.join(source_dir, "cover.jpg")
            self.create_test_cover_art(cover_file)

            # Process the directory
            result = process_directory(source_dir, dest_dir, force=True)

            # Verify results
            assert result["processed"] == 1
            assert result["skipped"] == 0
            assert result["cover_art_copied"] == True
            assert len(result["errors"]) == 0

            # Verify output files exist
            expected_opus = os.path.join(dest_dir, "test.opus")
            expected_cover = os.path.join(dest_dir, "cover.jpg")

            assert os.path.exists(expected_opus), "Opus file should be created"
            assert os.path.exists(expected_cover), "Cover art should be copied"

            # Verify opus file is not empty
            assert os.path.getsize(expected_opus) > 0, "Opus file should not be empty"

    def test_process_directory_with_metadata(self):
        """Test processing with metadata.txt file."""
        from music_librarian.cli import process_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source and destination directories
            source_dir = os.path.join(temp_dir, "source")
            dest_dir = os.path.join(temp_dir, "dest")
            os.makedirs(source_dir)

            # Create test FLAC file
            flac_file = os.path.join(source_dir, "track.flac")
            self.create_test_flac_file(flac_file)

            # Create metadata.txt
            metadata_content = """title: Test Album
artist: Test Artist
date: 2023

file: track.flac:
title: Test Track
track number: 01
"""
            metadata_file = os.path.join(source_dir, "metadata.txt")
            with open(metadata_file, "w") as f:
                f.write(metadata_content)

            # Process the directory
            result = process_directory(source_dir, dest_dir, force=True)

            # Verify results
            assert result["processed"] == 1
            assert len(result["errors"]) == 0

            # Verify output file exists
            expected_opus = os.path.join(dest_dir, "track.opus")
            assert os.path.exists(expected_opus), "Opus file should be created"

    def test_process_directory_skip_existing(self):
        """Test that existing files are skipped when force=False."""
        from music_librarian.cli import process_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source and destination directories
            source_dir = os.path.join(temp_dir, "source")
            dest_dir = os.path.join(temp_dir, "dest")
            os.makedirs(source_dir)
            os.makedirs(dest_dir)

            # Create test FLAC file
            flac_file = os.path.join(source_dir, "test.flac")
            self.create_test_flac_file(flac_file)

            # Create existing opus file
            existing_opus = os.path.join(dest_dir, "test.opus")
            with open(existing_opus, "w") as f:
                f.write("existing content")

            # Process the directory without force
            result = process_directory(source_dir, dest_dir, force=False)

            # Verify results - should skip existing file
            assert result["processed"] == 0
            assert result["skipped"] == 1
            assert len(result["errors"]) == 0

            # Verify existing file is unchanged
            with open(existing_opus, "r") as f:
                content = f.read()
            assert content == "existing content"

    def test_process_directory_force_overwrite(self):
        """Test that existing files are overwritten when force=True."""
        from music_librarian.cli import process_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source and destination directories
            source_dir = os.path.join(temp_dir, "source")
            dest_dir = os.path.join(temp_dir, "dest")
            os.makedirs(source_dir)
            os.makedirs(dest_dir)

            # Create test FLAC file
            flac_file = os.path.join(source_dir, "test.flac")
            self.create_test_flac_file(flac_file)

            # Create existing opus file
            existing_opus = os.path.join(dest_dir, "test.opus")
            with open(existing_opus, "w") as f:
                f.write("existing content")

            original_size = os.path.getsize(existing_opus)

            # Process the directory with force
            result = process_directory(source_dir, dest_dir, force=True)

            # Verify results - should process the file
            assert result["processed"] == 1
            assert result["skipped"] == 0
            assert len(result["errors"]) == 0

            # Verify file was overwritten (different size)
            new_size = os.path.getsize(existing_opus)
            assert new_size != original_size, "File should have been overwritten"

    def test_get_opus_quality_from_env(self):
        """Test reading OPUS_QUALITY from environment variable."""
        from music_librarian.cli import get_opus_quality

        # Test default quality when env var not set
        old_value = os.environ.get("OPUS_QUALITY")
        try:
            if "OPUS_QUALITY" in os.environ:
                del os.environ["OPUS_QUALITY"]

            quality = get_opus_quality()
            assert quality == "128"  # Default value

            # Test reading from environment
            os.environ["OPUS_QUALITY"] = "192"
            quality = get_opus_quality()
            assert quality == "192"

        finally:
            # Restore original value
            if old_value is not None:
                os.environ["OPUS_QUALITY"] = old_value
            elif "OPUS_QUALITY" in os.environ:
                del os.environ["OPUS_QUALITY"]


class TestFileDiscovery:
    """Tests for file discovery functionality."""

    def create_temp_dir_with_files(self, file_structure):
        """Helper to create a temporary directory with specified files.

        Args:
            file_structure: Dict mapping relative paths to file content (or None for empty files)

        Returns:
            Path to the temporary directory root
        """
        temp_dir = Path(tempfile.mkdtemp())

        for file_path, content in file_structure.items():
            full_path = temp_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if content is None:
                full_path.touch()
            else:
                full_path.write_text(content)

        return temp_dir

    def teardown_method(self):
        """Clean up any temporary directories created during tests."""
        # Individual tests will clean up their own temp dirs
        pass

    def test_find_flac_files_in_flat_directory(self):
        """Test finding FLAC files in a directory with no subdirectories."""

        file_structure = {
            "track1.flac": None,
            "track2.flac": None,
            "track3.wav": None,
            "cover.jpg": None,
        }

        temp_dir = self.create_temp_dir_with_files(file_structure)

        try:
            result = find_audio_files(temp_dir)
            expected = [Path("track1.flac"), Path("track2.flac"), Path("track3.wav")]
            assert sorted(result) == sorted(expected)
        finally:
            shutil.rmtree(temp_dir)

    def test_find_files_recursively(self):
        """Test finding audio files in nested directory structure."""

        file_structure = {
            "album1/track1.flac": None,
            "album1/track2.wav": None,
            "album1/cover.jpg": None,
            "album2/cd1/track1.flac": None,
            "album2/cd1/track2.flac": None,
            "album2/cd2/track1.wav": None,
            "single_track.flac": None,
        }

        temp_dir = self.create_temp_dir_with_files(file_structure)

        try:
            result = find_audio_files(temp_dir)
            expected = [
                Path("album1/track1.flac"),
                Path("album1/track2.wav"),
                Path("album2/cd1/track1.flac"),
                Path("album2/cd1/track2.flac"),
                Path("album2/cd2/track1.wav"),
                Path("single_track.flac"),
            ]
            assert sorted(result) == sorted(expected)
        finally:
            shutil.rmtree(temp_dir)

    def test_mixed_case_extensions(self):
        """Test finding files with mixed case extensions."""

        file_structure = {
            "track1.flac": None,
            "track2.FLAC": None,
            "track3.Flac": None,
            "track4.wav": None,
            "track5.WAV": None,
            "track6.Wav": None,
        }

        temp_dir = self.create_temp_dir_with_files(file_structure)

        try:
            result = find_audio_files(temp_dir)
            expected = [
                Path("track1.flac"),
                Path("track2.FLAC"),
                Path("track3.Flac"),
                Path("track4.wav"),
                Path("track5.WAV"),
                Path("track6.Wav"),
            ]
            assert sorted(result) == sorted(expected)
        finally:
            shutil.rmtree(temp_dir)

    def test_empty_directory(self):
        """Test behavior with completely empty directory."""

        temp_dir = self.create_temp_dir_with_files({})

        try:
            result = find_audio_files(temp_dir)
            assert result == []
        finally:
            shutil.rmtree(temp_dir)

    def test_directory_with_no_audio_files(self):
        """Test directory containing only non-audio files."""

        file_structure = {
            "readme.txt": "Some text",
            "cover.jpg": None,
            "metadata.txt": "Artist: Test",
            "subfolder/document.pdf": None,
        }

        temp_dir = self.create_temp_dir_with_files(file_structure)

        try:
            result = find_audio_files(temp_dir)
            assert result == []
        finally:
            shutil.rmtree(temp_dir)

    def test_nonexistent_directory(self):
        """Test behavior when given path to nonexistent directory."""

        nonexistent_path = Path("/this/path/does/not/exist")

        with pytest.raises(FileNotFoundError):
            find_audio_files(nonexistent_path)

    def test_include_lossy_audio_extensions(self):
        """Test that lossy audio files are included alongside lossless files."""

        file_structure = {
            "lossless1.flac": None,
            "lossless2.wav": None,
            "lossy1.mp3": None,  # Should be included
            "lossy2.m4a": None,  # Should be included
            "lossy3.ogg": None,  # Should be included
            "lossy4.aac": None,  # Should be included
            "lossy5.opus": None,  # Should be included
            "cover.jpg": None,  # Should be excluded
            "notes.txt": None,  # Should be excluded
        }

        temp_dir = self.create_temp_dir_with_files(file_structure)

        try:
            result = find_audio_files(temp_dir)
            expected = [
                Path("lossless1.flac"),
                Path("lossless2.wav"),
                Path("lossy1.mp3"),
                Path("lossy2.m4a"),
                Path("lossy3.ogg"),
                Path("lossy4.aac"),
                Path("lossy5.opus"),
            ]
            assert sorted(result) == sorted(expected)
        finally:
            shutil.rmtree(temp_dir)

    def test_find_audio_files_with_type_classification(self):
        """Test that audio files are classified as lossless or lossy."""
        from music_librarian.file_discovery import find_audio_files_with_types

        file_structure = {
            "track1.flac": None,
            "track2.wav": None,
            "track3.mp3": None,
            "track4.ogg": None,
            "cover.jpg": None,
        }

        temp_dir = self.create_temp_dir_with_files(file_structure)

        try:
            result = find_audio_files_with_types(temp_dir)

            expected = {
                "lossless": [Path("track1.flac"), Path("track2.wav")],
                "lossy": [Path("track3.mp3"), Path("track4.ogg")],
            }

            assert sorted(result["lossless"]) == sorted(expected["lossless"])
            assert sorted(result["lossy"]) == sorted(expected["lossy"])
        finally:
            shutil.rmtree(temp_dir)

    def test_is_lossless_format(self):
        """Test file format classification helper function."""
        from music_librarian.file_discovery import is_lossless_format

        # Test lossless formats
        assert is_lossless_format(Path("test.flac")) == True
        assert is_lossless_format(Path("test.FLAC")) == True
        assert is_lossless_format(Path("test.wav")) == True
        assert is_lossless_format(Path("test.WAV")) == True

        # Test lossy formats
        assert is_lossless_format(Path("test.mp3")) == False
        assert is_lossless_format(Path("test.ogg")) == False
        assert is_lossless_format(Path("test.aac")) == False
        assert is_lossless_format(Path("test.m4a")) == False
        assert is_lossless_format(Path("test.opus")) == False

        # Test non-audio files
        assert is_lossless_format(Path("test.jpg")) == False
        assert is_lossless_format(Path("test.txt")) == False

    def test_preserve_relative_paths(self):
        """Test that returned paths are relative to the search root."""

        file_structure = {
            "artist/album/track.flac": None,
            "artist/album/subfolder/track.wav": None,
        }

        temp_dir = self.create_temp_dir_with_files(file_structure)

        try:
            result = find_audio_files(temp_dir)
            expected = [
                Path("artist/album/track.flac"),
                Path("artist/album/subfolder/track.wav"),
            ]
            assert sorted(result) == sorted(expected)
        finally:
            shutil.rmtree(temp_dir)


class TestLossyMetadataHandling:
    """Tests for metadata handling on lossy audio files."""

    def test_apply_metadata_to_mp3(self):
        """Test applying metadata overrides to MP3 files."""
        from music_librarian.metadata_handler import apply_metadata_to_file

        # This test will verify the interface exists and basic functionality
        # Real files will be needed for full integration testing
        metadata = {
            "title": "Test Track",
            "artist": "Test Artist",
            "album": "Test Album",
            "date": "2023",
            "track number": "01",
        }

        # Test that the function signature exists and accepts expected parameters
        # Implementation will be added later
        assert callable(apply_metadata_to_file)

    def test_copy_lossy_file_with_metadata(self):
        """Test copying lossy file and applying metadata in one operation."""
        from music_librarian.audio_processor import copy_with_metadata

        # Test interface exists
        assert callable(copy_with_metadata)

    def test_supported_lossy_formats_for_metadata(self):
        """Test that metadata handler supports all required lossy formats."""
        from music_librarian.metadata_handler import supports_format

        # Test that all lossy formats are supported
        assert supports_format("mp3") == True
        assert supports_format("ogg") == True
        assert supports_format("aac") == True
        assert supports_format("m4a") == True
        assert supports_format("opus") == True

        # Test unsupported formats
        assert supports_format("jpg") == False
        assert supports_format("txt") == False


class TestMixedFormatProcessing:
    """Integration tests for processing directories with mixed audio formats."""

    def test_process_mixed_directory_lossless_and_lossy(self):
        """Test processing directory with both lossless and lossy files."""
        from music_librarian.cli import process_directory

        # This will test the updated process_directory function
        # that handles both transcoding and copying
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, "source")
            dest_dir = os.path.join(temp_dir, "dest")
            os.makedirs(source_dir)

            # Create test files - will need actual audio files for real test
            # For now, test the expected interface changes

            # Test files would include:
            # - track1.flac (should be transcoded to .opus)
            # - track2.mp3 (should be copied as .mp3)
            # - cover.jpg (should be copied)

            # Expected result structure verification
            result = process_directory(source_dir, dest_dir, force=True)

            # Verify result structure includes new keys for different file types
            assert "transcoded" in result or "processed" in result
            assert "copied" in result or "processed" in result
            assert "errors" in result

    def test_resolve_output_filename_preserves_lossy_extensions(self):
        """Test that lossy files keep their original extensions."""
        from music_librarian.cli import resolve_output_filename_for_type

        # Test that lossless files get .opus extension
        assert (
            resolve_output_filename_for_type("track.flac", "lossless") == "track.opus"
        )
        assert resolve_output_filename_for_type("track.wav", "lossless") == "track.opus"

        # Test that lossy files preserve their extension
        assert resolve_output_filename_for_type("track.mp3", "lossy") == "track.mp3"
        assert resolve_output_filename_for_type("track.ogg", "lossy") == "track.ogg"
        assert resolve_output_filename_for_type("track.aac", "lossy") == "track.aac"

    def test_rsgain_processes_mixed_audio_files(self):
        """Test that ReplayGain processing handles mixed output formats."""
        from music_librarian.cli import build_rsgain_command_for_mixed_formats

        # Test that rsgain can process directories with .opus, .mp3, .ogg, etc.
        directory = "/dest/album"
        result = build_rsgain_command_for_mixed_formats(directory)

        # Should still use the same rsgain easy command
        expected = ["rsgain", "easy", directory]
        assert result == expected


class TestExtractMetadataCLI:
    """Tests for the extract-metadata command CLI interface."""

    def test_extract_metadata_command_exists(self):
        """Test that extract-metadata command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "extract-metadata" in result.output

    def test_extract_metadata_requires_source_directory(self):
        """Test that extract-metadata command requires at least one source directory."""
        runner = CliRunner()
        result = runner.invoke(cli, ["extract-metadata"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_extract_metadata_accepts_single_directory(self):
        """Test that extract-metadata accepts a single source directory."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            test_dir = os.path.abspath("test_music")
            os.makedirs(test_dir)

            result = runner.invoke(cli, ["extract-metadata", test_dir])
            # Should not fail with argument parsing error
            assert "Missing argument" not in result.output

    def test_extract_metadata_accepts_multiple_directories(self):
        """Test that extract-metadata accepts multiple source directories."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            dir1 = os.path.abspath("music1")
            dir2 = os.path.abspath("music2")
            os.makedirs(dir1)
            os.makedirs(dir2)

            result = runner.invoke(cli, ["extract-metadata", dir1, dir2])
            # Should not fail with argument parsing error
            assert "Missing argument" not in result.output

    def test_extract_metadata_force_flag(self):
        """Test that --force flag is properly parsed."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            test_dir = os.path.abspath("test_music")
            os.makedirs(test_dir)

            result = runner.invoke(cli, ["extract-metadata", "--force", test_dir])
            # Test will need to check force flag is passed to processing function
            assert "Missing argument" not in result.output

    def test_extract_metadata_template_only_flag(self):
        """Test that --template-only flag is properly parsed."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            test_dir = os.path.abspath("test_music")
            os.makedirs(test_dir)

            result = runner.invoke(
                cli, ["extract-metadata", "--template-only", test_dir]
            )
            # Test will need to check template-only flag is passed to processing function
            assert "Missing argument" not in result.output

    def test_extract_metadata_help(self):
        """Test that extract-metadata command shows proper help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["extract-metadata", "--help"])
        assert result.exit_code == 0
        assert "Generate metadata.txt files" in result.output
        assert "--force" in result.output
        assert "--template-only" in result.output


class TestMetadataExtraction:
    """Tests for metadata extraction functionality."""

    def test_discover_audio_files_sorted(self):
        """Test that audio files are discovered and sorted alphabetically."""
        from music_librarian.cli import discover_and_sort_audio_files

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files in non-alphabetical order
            test_files = ["03-track.flac", "01-track.wav", "02-track.mp3"]
            for filename in test_files:
                Path(temp_dir) / filename
                (Path(temp_dir) / filename).touch()

            result = discover_and_sort_audio_files(temp_dir)
            expected = [
                Path("01-track.wav"),
                Path("02-track.mp3"),
                Path("03-track.flac"),
            ]
            assert result == expected

    def test_extract_metadata_from_audio_file(self):
        """Test extracting metadata from a single audio file."""
        from music_librarian.cli import extract_metadata_from_file

        # This will test the interface - real implementation will need actual audio files
        metadata = extract_metadata_from_file("test.flac")

        # Should return dict with expected keys
        assert isinstance(metadata, dict)
        expected_keys = ["title", "artist", "album", "date", "track number"]
        for key in expected_keys:
            assert key in metadata or metadata.get(key) is not None

    def test_generate_metadata_template_basic(self):
        """Test generating basic metadata.txt template."""
        from music_librarian.cli import generate_metadata_template

        audio_files = [Path("01-track.flac"), Path("02-track.wav")]
        album_metadata = {
            "title": "Test Album",
            "artist": "Test Artist",
            "date": "2023",
        }
        file_metadata = {
            "01-track.flac": {"title": "Track 1", "track number": "01"},
            "02-track.wav": {"title": "Track 2", "track number": "02"},
        }

        result = generate_metadata_template(audio_files, album_metadata, file_metadata)

        # Check that template includes comments and sections
        assert "# This file contains metadata overrides" in result
        assert "# Album metadata" in result
        assert "title: Test Album" in result
        assert "file: 01-track.flac:" in result
        assert "file: 02-track.wav:" in result

    def test_generate_metadata_template_empty(self):
        """Test generating empty template with --template-only."""
        from music_librarian.cli import generate_metadata_template

        audio_files = [Path("track.flac")]
        album_metadata = {}
        file_metadata = {}

        result = generate_metadata_template(
            audio_files, album_metadata, file_metadata, template_only=True
        )

        # Should include comments and empty sections
        assert "# This file contains metadata overrides" in result
        assert "title:" in result
        assert "artist:" in result
        assert "file: track.flac:" in result

    def test_extract_metadata_no_audio_files_error(self):
        """Test that processing fails when no audio files are found."""
        from music_librarian.cli import extract_metadata_from_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create directory with no audio files
            (Path(temp_dir) / "readme.txt").touch()

            with pytest.raises(ValueError, match="No audio files found"):
                extract_metadata_from_directory(temp_dir)

    def test_extract_metadata_existing_file_without_force(self):
        """Test that existing metadata.txt is not overwritten without --force."""
        from music_librarian.cli import extract_metadata_from_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create audio file and existing metadata.txt
            (Path(temp_dir) / "track.flac").touch()
            metadata_file = Path(temp_dir) / "metadata.txt"
            metadata_file.write_text("existing content")

            # Should skip existing file
            result = extract_metadata_from_directory(temp_dir, force=False)
            assert "skipped" in result
            assert metadata_file.read_text() == "existing content"

    def test_extract_metadata_existing_file_with_force(self):
        """Test that existing metadata.txt is overwritten with --force."""
        from music_librarian.cli import extract_metadata_from_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create audio file and existing metadata.txt
            (Path(temp_dir) / "track.flac").touch()
            metadata_file = Path(temp_dir) / "metadata.txt"
            metadata_file.write_text("existing content")

            # Should overwrite existing file
            result = extract_metadata_from_directory(temp_dir, force=True)
            assert "processed" in result
            assert metadata_file.read_text() != "existing content"

    def test_extract_metadata_with_nested_album_directories(self):
        """Test NEW behavior: creates metadata.txt in each directory with audio files."""
        from music_librarian.cli import extract_metadata_from_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create artist directory with multiple albums
            artist_dir = Path(temp_dir) / "Pink Floyd"
            album1_dir = artist_dir / "Dark Side of the Moon"
            album2_dir = artist_dir / "Wish You Were Here"

            album1_dir.mkdir(parents=True)
            album2_dir.mkdir(parents=True)

            # Create audio files in each album directory
            (album1_dir / "01-speak_to_me.flac").touch()
            (album1_dir / "02-breathe.flac").touch()
            (album2_dir / "01-shine_on.flac").touch()
            (album2_dir / "02-wish_you_were_here.flac").touch()

            # Also put some files in the artist root directory
            (artist_dir / "compilation_track.flac").touch()

            # Process the artist directory
            result = extract_metadata_from_directory(str(artist_dir))

            # NEW BEHAVIOR: Creates metadata.txt in each directory that contains audio files
            # Should process 3 directories: artist root, album1, album2
            assert result["processed"] == 3
            assert (artist_dir / "metadata.txt").exists()
            assert (album1_dir / "metadata.txt").exists()
            assert (album2_dir / "metadata.txt").exists()

            # Each metadata.txt should contain only files from its own directory
            artist_content = (artist_dir / "metadata.txt").read_text()
            assert "compilation_track.flac" in artist_content
            assert (
                "speak_to_me" not in artist_content
            )  # Should not include subdirectory files

            album1_content = (album1_dir / "metadata.txt").read_text()
            assert "01-speak_to_me.flac" in album1_content
            assert "02-breathe.flac" in album1_content
            assert (
                "compilation_track" not in album1_content
            )  # Should not include parent files

            album2_content = (album2_dir / "metadata.txt").read_text()
            assert "01-shine_on.flac" in album2_content
            assert "02-wish_you_were_here.flac" in album2_content
            assert (
                "compilation_track" not in album2_content
            )  # Should not include parent files

    def test_extract_metadata_only_subdirectories_no_root_files(self):
        """Test NEW behavior: creates metadata.txt only in subdirectories with audio files."""
        from music_librarian.cli import extract_metadata_from_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create artist directory with albums but no files in root
            artist_dir = Path(temp_dir) / "Pink Floyd"
            album1_dir = artist_dir / "Dark Side of the Moon"
            album2_dir = artist_dir / "Wish You Were Here"

            album1_dir.mkdir(parents=True)
            album2_dir.mkdir(parents=True)

            # Create audio files only in subdirectories
            (album1_dir / "01-speak_to_me.flac").touch()
            (album2_dir / "01-shine_on.flac").touch()

            # Process the artist directory
            # NEW BEHAVIOR: Creates metadata.txt only in directories that contain audio files
            result = extract_metadata_from_directory(str(artist_dir))

            assert result["processed"] == 2  # Two album directories processed
            assert not (
                artist_dir / "metadata.txt"
            ).exists()  # No files in root, so no metadata.txt
            assert (album1_dir / "metadata.txt").exists()
            assert (album2_dir / "metadata.txt").exists()

            # Each metadata.txt should contain only files from its own directory
            album1_content = (album1_dir / "metadata.txt").read_text()
            assert "01-speak_to_me.flac" in album1_content
            assert (
                "shine_on" not in album1_content
            )  # Should not include other album files

            album2_content = (album2_dir / "metadata.txt").read_text()
            assert "01-shine_on.flac" in album2_content
            assert (
                "speak_to_me" not in album2_content
            )  # Should not include other album files

    def test_extract_metadata_per_album_recursive_processing(self):
        """Test that metadata.txt files are created for each directory containing audio files."""
        from music_librarian.cli import extract_metadata_from_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create Pink Floyd directory structure as described
            pf_dir = Path(temp_dir) / "Pink Floyd"
            dsotm_dir = pf_dir / "The Dark Side of the Moon"
            wywh_dir = pf_dir / "Wish You Were Here - Immersion Box Set"
            disc1_dir = wywh_dir / "Disc 1"
            disc2_dir = wywh_dir / "Disc 2"

            # Create all directories
            disc1_dir.mkdir(parents=True)
            disc2_dir.mkdir(parents=True)
            dsotm_dir.mkdir(parents=True)

            # Create audio files in each "album" directory
            (pf_dir / "Daybreak.mp3").touch()
            (dsotm_dir / "01 - Speak to Me.flac").touch()
            (dsotm_dir / "02 - Breathe.flac").touch()
            (disc1_dir / "01 - Shine On You Crazy Diamond.flac").touch()
            (disc1_dir / "02 - Welcome to the Machine.flac").touch()
            (
                disc2_dir / "Shine On You Crazy Diamond (Live At Wembley 1974).flac"
            ).touch()

            # Process the Pink Floyd directory
            result = extract_metadata_from_directory(str(pf_dir))

            # Should create metadata.txt in each directory that directly contains audio files
            assert result["processed"] == 4  # 4 album directories processed
            assert result["skipped"] == 0
            assert len(result["errors"]) == 0

            # Verify metadata.txt files were created in correct locations
            assert (pf_dir / "metadata.txt").exists()
            assert (dsotm_dir / "metadata.txt").exists()
            assert (disc1_dir / "metadata.txt").exists()
            assert (disc2_dir / "metadata.txt").exists()

            # Verify NO metadata.txt files were created in intermediate directories
            assert not (wywh_dir / "metadata.txt").exists()

            # Verify each metadata.txt contains only files from its own directory
            pf_content = (pf_dir / "metadata.txt").read_text()
            assert "Daybreak.mp3" in pf_content
            assert (
                "Speak to Me" not in pf_content
            )  # Should not include subdirectory files

            dsotm_content = (dsotm_dir / "metadata.txt").read_text()
            assert "01 - Speak to Me.flac" in dsotm_content
            assert "02 - Breathe.flac" in dsotm_content
            assert (
                "Daybreak.mp3" not in dsotm_content
            )  # Should not include parent dir files

    def test_extract_metadata_mixed_structure_with_empty_dirs(self):
        """Test processing with directories that don't contain audio files."""
        from music_librarian.cli import extract_metadata_from_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create structure with some empty directories
            artist_dir = Path(temp_dir) / "Artist"
            album_dir = artist_dir / "Album"
            empty_dir = artist_dir / "Empty Dir"
            another_album = artist_dir / "Another Album"

            album_dir.mkdir(parents=True)
            empty_dir.mkdir(parents=True)
            another_album.mkdir(parents=True)

            # Only put audio files in some directories
            (album_dir / "track1.flac").touch()
            (another_album / "track1.wav").touch()
            # empty_dir has no audio files
            (empty_dir / "readme.txt").touch()  # Non-audio file

            result = extract_metadata_from_directory(str(artist_dir))

            # Should only process directories that contain audio files
            assert result["processed"] == 2
            assert (album_dir / "metadata.txt").exists()
            assert (another_album / "metadata.txt").exists()
            assert not (empty_dir / "metadata.txt").exists()
            assert not (artist_dir / "metadata.txt").exists()  # No direct audio files

    def test_extract_metadata_deeply_nested_structure(self):
        """Test processing with deeply nested album structure."""
        from music_librarian.cli import extract_metadata_from_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create deeply nested structure
            level1 = Path(temp_dir) / "Artists"
            level2 = level1 / "Pink Floyd"
            level3 = level2 / "Box Sets"
            level4 = level3 / "Immersion"
            level5 = level4 / "Dark Side of the Moon"
            level6 = level5 / "Disc 1"

            level6.mkdir(parents=True)

            # Put audio files at different levels
            (level1 / "compilation.mp3").touch()  # Artists/ level
            (level3 / "rare_track.flac").touch()  # Box Sets/ level
            (level6 / "track1.flac").touch()  # Disc 1/ level

            result = extract_metadata_from_directory(str(level1))

            # Should create metadata.txt in each directory with direct audio files
            assert result["processed"] == 3
            assert (level1 / "metadata.txt").exists()
            assert (level3 / "metadata.txt").exists()
            assert (level6 / "metadata.txt").exists()

            # Should NOT create in intermediate directories without direct audio files
            assert not (level2 / "metadata.txt").exists()
            assert not (level4 / "metadata.txt").exists()
            assert not (level5 / "metadata.txt").exists()


class TestCoverMetadataHandling:
    """Tests for cover image metadata handling in extract-metadata and export."""

    def test_extract_metadata_adds_cover_field_with_existing_cover(self):
        """Test that extract-metadata adds cover field when recognizable cover exists."""
        from music_librarian.cli import extract_metadata_from_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files
            (temp_path / "track1.flac").write_bytes(b"fake flac data")
            (temp_path / "cover.jpg").write_bytes(b"fake jpg data")

            # Run extract-metadata
            result = extract_metadata_from_directory(str(temp_path), force=True)

            # Check that metadata.txt was created and contains cover field
            metadata_file = temp_path / "metadata.txt"
            assert metadata_file.exists()

            content = metadata_file.read_text()
            assert "cover: cover.jpg" in content
            assert result["processed"] == 1

    def test_extract_metadata_adds_blank_cover_field_when_no_cover(self):
        """Test that extract-metadata adds blank cover field when no recognizable cover exists."""
        from music_librarian.cli import extract_metadata_from_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files without recognizable cover
            (temp_path / "track1.flac").write_bytes(b"fake flac data")
            (temp_path / "randomimage.jpg").write_bytes(b"fake jpg data")

            # Run extract-metadata
            result = extract_metadata_from_directory(str(temp_path), force=True)

            # Check that metadata.txt was created and contains blank cover field
            metadata_file = temp_path / "metadata.txt"
            assert metadata_file.exists()

            content = metadata_file.read_text()
            assert "cover:" in content
            assert "cover: randomimage.jpg" not in content
            assert result["processed"] == 1

    def test_extract_metadata_prioritizes_cover_files(self):
        """Test that extract-metadata prioritizes standard cover files over others."""
        from music_librarian.cli import extract_metadata_from_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create test files with multiple potential covers
            (temp_path / "track1.flac").write_bytes(b"fake flac data")
            (temp_path / "folder.jpg").write_bytes(b"fake jpg data")
            (temp_path / "cover.png").write_bytes(b"fake png data")

            # Run extract-metadata
            result = extract_metadata_from_directory(str(temp_path), force=True)

            # Check that metadata.txt prioritizes cover.png over folder.jpg
            metadata_file = temp_path / "metadata.txt"
            content = metadata_file.read_text()
            assert "cover: cover.png" in content
            assert "cover: folder.jpg" not in content

    def test_export_copies_and_renames_cover_from_metadata(self):
        """Test that export copies and renames cover file specified in metadata."""
        from music_librarian.cli import process_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import os

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            dest_dir = temp_path / "dest"
            source_dir.mkdir()
            dest_dir.mkdir()

            # Create test files
            (source_dir / "track1.flac").write_bytes(b"fake flac data")
            (source_dir / "AlbumArtwork.jpg").write_bytes(b"fake jpg data")

            # Create metadata.txt with cover specification
            metadata_content = """
title: Test Album
artist: Test Artist
cover: AlbumArtwork.jpg

track1.flac
title: Track 1
"""
            (source_dir / "metadata.txt").write_text(metadata_content.strip())

            # Set environment variables
            os.environ["MUSIC_SOURCE_ROOT"] = str(temp_path)
            os.environ["MUSIC_DEST_ROOT"] = str(temp_path)

            try:
                # Run export
                result = process_directory(str(source_dir), str(dest_dir), force=True)

                # Check that cover was copied and renamed
                assert (dest_dir / "cover.jpg").exists()
                assert not (dest_dir / "AlbumArtwork.jpg").exists()

                # Verify content is the same
                original_content = (source_dir / "AlbumArtwork.jpg").read_bytes()
                copied_content = (dest_dir / "cover.jpg").read_bytes()
                assert original_content == copied_content

            finally:
                # Clean up environment variables
                if "MUSIC_SOURCE_ROOT" in os.environ:
                    del os.environ["MUSIC_SOURCE_ROOT"]
                if "MUSIC_DEST_ROOT" in os.environ:
                    del os.environ["MUSIC_DEST_ROOT"]

    def test_export_handles_different_cover_extensions(self):
        """Test that export preserves file extension when renaming cover."""
        from music_librarian.cli import process_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import os

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            dest_dir = temp_path / "dest"
            source_dir.mkdir()
            dest_dir.mkdir()

            # Create test files
            (source_dir / "track1.flac").write_bytes(b"fake flac data")
            (source_dir / "MyCustomCover.png").write_bytes(b"fake png data")

            # Create metadata.txt with cover specification
            metadata_content = """
title: Test Album
artist: Test Artist
cover: MyCustomCover.png

track1.flac
title: Track 1
"""
            (source_dir / "metadata.txt").write_text(metadata_content.strip())

            # Set environment variables
            os.environ["MUSIC_SOURCE_ROOT"] = str(temp_path)
            os.environ["MUSIC_DEST_ROOT"] = str(temp_path)

            try:
                # Run export
                result = process_directory(str(source_dir), str(dest_dir), force=True)

                # Check that cover was copied and renamed with correct extension
                assert (dest_dir / "cover.png").exists()
                assert not (dest_dir / "MyCustomCover.png").exists()

            finally:
                # Clean up environment variables
                if "MUSIC_SOURCE_ROOT" in os.environ:
                    del os.environ["MUSIC_SOURCE_ROOT"]
                if "MUSIC_DEST_ROOT" in os.environ:
                    del os.environ["MUSIC_DEST_ROOT"]

    def test_export_skips_cover_when_not_specified(self):
        """Test that export uses existing cover art logic when no cover specified in metadata."""
        from music_librarian.cli import process_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import os

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            dest_dir = temp_path / "dest"
            source_dir.mkdir()
            dest_dir.mkdir()

            # Create test files
            (source_dir / "track1.flac").write_bytes(b"fake flac data")
            (source_dir / "cover.jpg").write_bytes(b"fake jpg data")

            # Create metadata.txt WITHOUT cover specification
            metadata_content = """
title: Test Album
artist: Test Artist

track1.flac
title: Track 1
"""
            (source_dir / "metadata.txt").write_text(metadata_content.strip())

            # Set environment variables
            os.environ["MUSIC_SOURCE_ROOT"] = str(temp_path)
            os.environ["MUSIC_DEST_ROOT"] = str(temp_path)

            try:
                # Run export
                result = process_directory(str(source_dir), str(dest_dir), force=True)

                # Check that existing cover art logic was used
                assert (dest_dir / "cover.jpg").exists()

            finally:
                # Clean up environment variables
                if "MUSIC_SOURCE_ROOT" in os.environ:
                    del os.environ["MUSIC_SOURCE_ROOT"]
                if "MUSIC_DEST_ROOT" in os.environ:
                    del os.environ["MUSIC_DEST_ROOT"]

    def test_export_handles_missing_cover_file_gracefully(self):
        """Test that export handles missing cover file gracefully."""
        from music_librarian.cli import process_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import os

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            dest_dir = temp_path / "dest"
            source_dir.mkdir()
            dest_dir.mkdir()

            # Create test files
            (source_dir / "track1.flac").write_bytes(b"fake flac data")

            # Create metadata.txt with cover specification but no actual file
            metadata_content = """
title: Test Album
artist: Test Artist
cover: NonExistentCover.jpg

track1.flac
title: Track 1
"""
            (source_dir / "metadata.txt").write_text(metadata_content.strip())

            # Set environment variables
            os.environ["MUSIC_SOURCE_ROOT"] = str(temp_path)
            os.environ["MUSIC_DEST_ROOT"] = str(temp_path)

            try:
                # Run export - should not fail completely
                result = process_directory(str(source_dir), str(dest_dir), force=True)

                # Check that the cover error was logged
                cover_errors = [
                    error
                    for error in result["errors"]
                    if "Cover file specified" in error
                ]
                assert len(cover_errors) == 1
                assert "NonExistentCover.jpg" in cover_errors[0]

                # Check that no cover file was created
                assert not (dest_dir / "cover.jpg").exists()

            finally:
                # Clean up environment variables
                if "MUSIC_SOURCE_ROOT" in os.environ:
                    del os.environ["MUSIC_SOURCE_ROOT"]
                if "MUSIC_DEST_ROOT" in os.environ:
                    del os.environ["MUSIC_DEST_ROOT"]


class TestNestedMetadataHandling:
    """Tests for handling metadata.txt files in nested directory structures."""

    def create_test_flac_file(self, filepath):
        """Create a minimal test FLAC file using ffmpeg."""
        # Generate 1 second of silence as FLAC
        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            "1",
            "-c:a",
            "flac",
            "-y",  # Overwrite without asking
            str(filepath),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def test_process_nested_albums_with_per_directory_metadata(self):
        """Test processing nested album directories with individual metadata.txt files."""
        from music_librarian.cli import process_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import os

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            dest_dir = temp_path / "dest"
            source_dir.mkdir()
            dest_dir.mkdir()

            # Create nested album structure
            album1_dir = source_dir / "Album 1"
            album2_dir = source_dir / "Album 2"
            album1_dir.mkdir()
            album2_dir.mkdir()

            # Create audio files
            self.create_test_flac_file(album1_dir / "track1.flac")
            self.create_test_flac_file(album1_dir / "track2.flac")
            self.create_test_flac_file(album2_dir / "track1.flac")

            # Create per-directory metadata.txt files
            album1_metadata = """
title: First Album
artist: Artist One
date: 2020

file: track1.flac:
title: First Track
track number: 01

file: track2.flac:
title: Second Track
track number: 02
"""
            (album1_dir / "metadata.txt").write_text(album1_metadata.strip())

            album2_metadata = """
title: Second Album
artist: Artist Two
date: 2021

file: track1.flac:
title: Different Track
track number: 01
"""
            (album2_dir / "metadata.txt").write_text(album2_metadata.strip())

            # Set environment variables
            os.environ["MUSIC_SOURCE_ROOT"] = str(temp_path)
            os.environ["MUSIC_DEST_ROOT"] = str(temp_path)

            try:
                # Run export
                result = process_directory(str(source_dir), str(dest_dir), force=True)

                # Verify processing succeeded
                assert result["processed"] == 3
                assert len(result["errors"]) == 0

                # Verify output files exist with correct names
                assert (dest_dir / "Album 1" / "track1.opus").exists()
                assert (dest_dir / "Album 1" / "track2.opus").exists()
                assert (dest_dir / "Album 2" / "track1.opus").exists()

            finally:
                # Clean up environment variables
                if "MUSIC_SOURCE_ROOT" in os.environ:
                    del os.environ["MUSIC_SOURCE_ROOT"]
                if "MUSIC_DEST_ROOT" in os.environ:
                    del os.environ["MUSIC_DEST_ROOT"]

    def test_mixed_metadata_scenarios(self):
        """Test processing with mix of top-level and per-directory metadata.txt files."""
        from music_librarian.cli import process_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import os

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            dest_dir = temp_path / "dest"
            source_dir.mkdir()
            dest_dir.mkdir()

            # Create mixed structure
            self.create_test_flac_file(source_dir / "root_track.flac")

            album_dir = source_dir / "Album"
            album_dir.mkdir()
            self.create_test_flac_file(album_dir / "album_track.flac")

            # Top-level metadata.txt (for root_track.flac)
            root_metadata = """
title: Root Album
artist: Root Artist

root_track.flac
title: Root Track
track number: 01
"""
            (source_dir / "metadata.txt").write_text(root_metadata.strip())

            # Album-level metadata.txt (for album_track.flac)
            album_metadata = """
title: Nested Album
artist: Nested Artist

album_track.flac
title: Album Track
track number: 01
"""
            (album_dir / "metadata.txt").write_text(album_metadata.strip())

            # Set environment variables
            os.environ["MUSIC_SOURCE_ROOT"] = str(temp_path)
            os.environ["MUSIC_DEST_ROOT"] = str(temp_path)

            try:
                # Run export
                result = process_directory(str(source_dir), str(dest_dir), force=True)

                # Verify both files processed with their respective metadata
                assert result["processed"] == 2
                assert len(result["errors"]) == 0

                # Verify output files exist
                assert (dest_dir / "root_track.opus").exists()
                assert (dest_dir / "Album" / "album_track.opus").exists()

            finally:
                # Clean up environment variables
                if "MUSIC_SOURCE_ROOT" in os.environ:
                    del os.environ["MUSIC_SOURCE_ROOT"]
                if "MUSIC_DEST_ROOT" in os.environ:
                    del os.environ["MUSIC_DEST_ROOT"]

    def test_no_metadata_files_in_nested_structure(self):
        """Test processing nested structure with no metadata.txt files (should use source metadata)."""
        from music_librarian.cli import process_directory
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import os

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            dest_dir = temp_path / "dest"
            source_dir.mkdir()
            dest_dir.mkdir()

            # Create nested structure without metadata.txt
            album_dir = source_dir / "Album"
            album_dir.mkdir()
            self.create_test_flac_file(album_dir / "track.flac")

            # Set environment variables
            os.environ["MUSIC_SOURCE_ROOT"] = str(temp_path)
            os.environ["MUSIC_DEST_ROOT"] = str(temp_path)

            try:
                # Run export
                result = process_directory(str(source_dir), str(dest_dir), force=True)

                # Should still process the file using source metadata
                assert result["processed"] == 1
                assert (dest_dir / "Album" / "track.opus").exists()

            finally:
                # Clean up environment variables
                if "MUSIC_SOURCE_ROOT" in os.environ:
                    del os.environ["MUSIC_SOURCE_ROOT"]
                if "MUSIC_DEST_ROOT" in os.environ:
                    del os.environ["MUSIC_DEST_ROOT"]
