"""Tests for metadata.txt generation reproducing the source tags on export."""

from audio_helpers import make_flac

from music_librarian.extractor import extract_metadata_from_single_directory
from music_librarian.metadata_file import merge_metadata, parse_metadata_file
from music_librarian.metadata_handler import read_metadata_from_file


def generated_metadata(directory):
    """Generate metadata.txt in `directory` and return it parsed."""
    result = extract_metadata_from_single_directory(directory)
    assert result["errors"] == []
    return parse_metadata_file((directory / "metadata.txt").read_text())


def exported_tags(directory, filename, metadata):
    """The tags `export` would write for `filename` given parsed metadata."""
    return merge_metadata(
        metadata["album"],
        metadata["files"].get(filename, {}),
        filename,
        str(directory / filename),
    )


def test_album_artist_comes_from_albumartist_tag(tmp_path):
    make_flac(
        tmp_path / "01.flac",
        artist="Arcana feat. Someone",
        albumartist="Arcana",
        album="Magna Silentia",
    )

    metadata = generated_metadata(tmp_path)

    assert metadata["album"]["artist"] == "Arcana"


def test_album_artist_falls_back_to_artist_tag(tmp_path):
    make_flac(tmp_path / "01.flac", artist="Arcana", album="Magna Silentia")

    metadata = generated_metadata(tmp_path)

    assert metadata["album"]["artist"] == "Arcana"


def test_track_artist_matching_album_artist_is_not_repeated(tmp_path):
    make_flac(tmp_path / "01.flac", artist="Arcana", albumartist="Arcana", album="M")

    metadata = generated_metadata(tmp_path)

    assert "artist" not in metadata["files"]["01.flac"]


def test_differing_track_artist_is_written_per_file(tmp_path):
    make_flac(tmp_path / "01.flac", artist="Arcana", albumartist="Arcana", album="M")
    make_flac(
        tmp_path / "02.flac",
        artist="Arcana & Guests",
        albumartist="Arcana",
        album="M",
    )

    metadata = generated_metadata(tmp_path)

    assert metadata["files"]["02.flac"]["artist"] == "Arcana & Guests"


def test_export_reproduces_per_track_artists(tmp_path):
    make_flac(
        tmp_path / "01.flac",
        artist="Perturbator",
        albumartist="Perturbator",
        album="TERROR 404",
        title="Opening Credits",
    )
    make_flac(
        tmp_path / "02.flac",
        artist="Perturbator & Lueur Verte",
        albumartist="Perturbator",
        album="TERROR 404",
        title="Mirage",
    )

    metadata = generated_metadata(tmp_path)

    for filename in ("01.flac", "02.flac"):
        source = read_metadata_from_file(str(tmp_path / filename))
        exported = exported_tags(tmp_path, filename, metadata)
        assert exported["artist"] == source["artist"]
        assert exported["albumartist"] == source["albumartist"]
