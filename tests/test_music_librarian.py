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
