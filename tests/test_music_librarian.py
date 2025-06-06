import os
import shutil
import tempfile
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


class TestTranscodeCLI:
    """Tests for the transcode command CLI interface."""

    def test_transcode_requires_source_directory(self):
        """Test that transcode command requires at least one source directory."""
        runner = CliRunner()
        result = runner.invoke(cli, ["transcode"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_transcode_missing_source_root_env(self):
        """Test that transcode fails when MUSIC_SOURCE_ROOT is not set."""
        runner = CliRunner()
        env = {"MUSIC_DEST_ROOT": "/dest"}
        result = runner.invoke(cli, ["transcode", "/some/path"], env=env)
        assert result.exit_code == 1
        assert "MUSIC_SOURCE_ROOT environment variable not set" in result.output

    def test_transcode_missing_dest_root_env(self):
        """Test that transcode fails when MUSIC_DEST_ROOT is not set."""
        runner = CliRunner()
        env = {"MUSIC_SOURCE_ROOT": "/source"}
        result = runner.invoke(cli, ["transcode", "/some/path"], env=env)
        assert result.exit_code == 1
        assert "MUSIC_DEST_ROOT environment variable not set" in result.output

    def test_transcode_source_not_under_root(self):
        """Test that transcode fails when source directory is not under MUSIC_SOURCE_ROOT."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_root = os.path.abspath("music_source")
            dest_root = os.path.abspath("music_dest")
            bad_source = os.path.abspath("other_location")

            os.makedirs(source_root)
            os.makedirs(dest_root)
            os.makedirs(bad_source)

            env = {"MUSIC_SOURCE_ROOT": source_root, "MUSIC_DEST_ROOT": dest_root}

            result = runner.invoke(cli, ["transcode", bad_source], env=env)
            assert result.exit_code == 1
            assert f"is not under MUSIC_SOURCE_ROOT" in result.output

    def test_transcode_valid_single_directory(self):
        """Test that transcode accepts valid single source directory."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_root = os.path.abspath("music_source")
            dest_root = os.path.abspath("music_dest")
            album_dir = os.path.join(source_root, "artist", "album")

            os.makedirs(album_dir)
            os.makedirs(dest_root)

            env = {"MUSIC_SOURCE_ROOT": source_root, "MUSIC_DEST_ROOT": dest_root}

            result = runner.invoke(cli, ["transcode", album_dir], env=env)
            # Should not exit with error for validation
            assert "is not under MUSIC_SOURCE_ROOT" not in result.output
            assert "environment variable not set" not in result.output

    def test_transcode_valid_multiple_directories(self):
        """Test that transcode accepts multiple valid source directories."""
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

            result = runner.invoke(cli, ["transcode", album1_dir, album2_dir], env=env)
            assert "is not under MUSIC_SOURCE_ROOT" not in result.output
            assert "environment variable not set" not in result.output

    def test_transcode_force_flag(self):
        """Test that --force flag is properly parsed."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_root = os.path.abspath("music_source")
            dest_root = os.path.abspath("music_dest")
            album_dir = os.path.join(source_root, "artist", "album")

            os.makedirs(album_dir)
            os.makedirs(dest_root)

            env = {"MUSIC_SOURCE_ROOT": source_root, "MUSIC_DEST_ROOT": dest_root}

            result = runner.invoke(cli, ["transcode", "--force", album_dir], env=env)
            assert "Force overwrite: True" in result.output

    def test_transcode_no_force_flag(self):
        """Test default behavior without --force flag."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_root = os.path.abspath("music_source")
            dest_root = os.path.abspath("music_dest")
            album_dir = os.path.join(source_root, "artist", "album")

            os.makedirs(album_dir)
            os.makedirs(dest_root)

            env = {"MUSIC_SOURCE_ROOT": source_root, "MUSIC_DEST_ROOT": dest_root}

            result = runner.invoke(cli, ["transcode", album_dir], env=env)
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

        expected = ["opusenc", "/source/track.flac", "/dest/track.opus"]

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
            "--comment",
            "TITLE=Track Title",
            "--comment",
            "ARTIST=Artist Name",
            "--comment",
            "ALBUM=Album Title",
            "--comment",
            "DATE=2023",
            "--comment",
            "TRACKNUMBER=01",
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
            "--comment",
            "TITLE=Test Track",
            "--comment",
            "ARTIST=Test Artist",
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
            "--comment",
            "TITLE=",
            "--comment",
            "ARTIST=Artist Name",
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


class TestTranscodeWorkflow:
    """Integration tests for complete transcoding workflow."""

    def test_process_directory_basic(self):
        """Test processing a directory with FLAC files."""
        from music_librarian.cli import process_directory

        # This test requires actual implementation to verify workflow
        # For now, test that the function exists and can be called
        try:
            from music_librarian.cli import process_directory
        except ImportError:
            pytest.fail("process_directory function not implemented")

    def test_get_opus_quality_from_env(self):
        """Test reading OPUS_QUALITY from environment variable."""
        from music_librarian.cli import get_opus_quality

        # Test default quality when env var not set
        quality = get_opus_quality()
        assert quality is not None  # Should have a reasonable default

        # Test reading from environment (would need to mock os.environ)
        # This is a placeholder for the actual implementation


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

    def test_exclude_non_audio_extensions(self):
        """Test that non-audio files are properly excluded."""

        file_structure = {
            "good.flac": None,
            "good.wav": None,
            "bad.mp3": None,  # Should be excluded
            "bad.m4a": None,  # Should be excluded
            "bad.ogg": None,  # Should be excluded
            "bad.aac": None,  # Should be excluded
            "cover.jpg": None,  # Should be excluded
            "notes.txt": None,  # Should be excluded
        }

        temp_dir = self.create_temp_dir_with_files(file_structure)

        try:
            result = find_audio_files(temp_dir)
            expected = [Path("good.flac"), Path("good.wav")]
            assert sorted(result) == sorted(expected)
        finally:
            shutil.rmtree(temp_dir)

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
